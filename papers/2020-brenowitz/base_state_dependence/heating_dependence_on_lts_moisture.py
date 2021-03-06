import torch
import numpy as np
import matplotlib.pyplot as plt
import altair as alt

from src.data import open_data, assign_apparent_sources
from uwnet.thermo import *

def open_data_with_lts_and_path():
    ds = open_data('training').sel(time=slice(120,140))
    p = open_data('pressure')

    # make necessary computations
    ds['p'] = p
    ds['lat'] = ngaqua_y_to_lat(ds.y)
    # compute LTS and Mid Trop moisture
    ds['lts'] = lower_tropospheric_stability(ds.TABS, p, ds.SST, ds.Ps)
    ds['path'] = midtropospheric_moisture(ds.QV, p, bottom=850, top=600)
    return ds


def subtropical_data():
    # load model and datya
    ds = open_data_with_lts_and_path().pipe(assign_apparent_sources)
    lat = ds.lat
    # select the sub-tropics
#     subtropics = (11 < np.abs(lat)) & (np.abs(lat) < 22.5)
    subtropics = (np.abs(lat) < 22.5) #& (np.abs(lat)>  11.25)
    tropics_lat = (np.abs(lat) < 11.25)

    return ds.isel(y=subtropics)


def compute_nn(model, averages, dims):
    if len(dims) == 1:
        return compute_nn_1d(model, averages, dims[0])
    else:
        return compute_nn_nd(model, averages, dims)


def compute_nn_nd(model, averages, dims):
    new_dim = 'time' # need to be called "time" unfortunately
    stacked = averages.stack({new_dim: dims}).expand_dims(['x', 'y'])\
        .transpose(new_dim, 'z', 'y', 'x')
    output = model.call_with_xr(stacked)
    return output.unstack(new_dim).squeeze()


def compute_nn_1d(model, averages, dim):
    avgs_expanded = averages.rename({dim: 'time'}).expand_dims(['x', 'y'], [-1, -2])
    return model.call_with_xr(avgs_expanded).rename({'time': dim}).squeeze()


def groupby_and_compute_nn(tropics, model, key, bins):
    bins_key = key + '_bins'
    averages = (tropics
     .stack(gridcell=['x', 'y', 'time'])
     .groupby_bins(key, bins=bins)
     .mean('gridcell'))

    output = compute_nn(model, averages, batch_dims=[bins_key])
    for key in output:
        NNkey = 'NN' + key
        averages[NNkey] = output[key]
        
    return averages


def plot_line_cmap(arr, lower_val=4, key='path_bins'):
    val = [bin.mid for bin in arr[key].values]
    for it, arr in arr.groupby(key):
        label = it.mid
        arr.plot(y='z', hue=key, color=plt.cm.inferno((it.mid + lower_val)/(25+lower_val)), label=label)
    plt.legend()

        
def groupby_2d(ds, fun, lts_bins, moisture_bins):
        
    def _average_over_lts_bins(ds):
        return ds.groupby_bins('lts', lts_bins).apply(fun)

    return (ds
     .stack(gridcell=['x', 'y', 'time'])
     .groupby_bins('path', bins=moisture_bins)
     .apply(_average_over_lts_bins))


def _to_plottable_dataframe(q2):

    df=  q2.to_dataframe().reset_index()
    df['lts']  = df.lts_bins
    df['path']  = df.path_bins
    df = df.drop(['lts_bins', 'path_bins'], axis=1)
    df = df.dropna()
    return df


def plot_line_by_key_altair(ds, key, title_fn=lambda x: '', cmap='viridis', c_sort="descending", c_title=''):
    """Make line plots of Q1 and Q2 for different levels of a dataset"""
    
    if not c_title:
        c_title = key
    
    df = _to_plottable_dataframe(ds)
    
    z = alt.Y('z', axis=alt.Axis(title='z (m)'))
    color = alt.Color(key, scale=alt.Scale(scheme=cmap), sort=c_sort, legend=alt.Legend(title=c_title))
    
    
    labels = [
        ('a', 'QT', 'g/kg','Total Water'),
        ('b', 'SLI', 'K', 'Liquid-Ice Static Energy'),
        ('c', 'Q1', 'K/day', 'Average Q₁'),
        ('d', 'Q2', 'g/kg/day', 'Average Q₂'),
        ('e', 'Q1NN', 'K/day', 'Q₁ Prediction'),
        ('f', 'Q2NN', 'g/kg/day', 'Q₂ Prediction')
    ]

    charts = []
    for letter, key, unit, label in labels:
        chart = (alt.Chart(df, width=150).mark_line()
         .encode(alt.X(key, axis=alt.Axis(title=unit)),
                 z,
                 color, order='z')
         .properties(title=f'{letter}) {label}')
        )
        charts.append(chart)

    row1 = alt.hconcat(*charts[:3])
    row2 = alt.hconcat(*charts[3:])
    return alt.vconcat(row1, row2, title=title_fn(ds))


def heating_weighted_height(q1, layer_mass):
    weight = np.maximum(q1,0)  * layer_mass
    weight = weight/weight.sum('z', skipna=False)
    metric = (weight*q1.z).sum('z', skipna=False)
    return metric.rename('heating_weighted_height')
    
    

def get_data():
    """Get data averaged over a (LTS, mid trop humidity) space"""
    lts_plot_path = "sensitivity_to_lts.pdf"
    moisture_plot_path = "sensitivity_to_moist.pdf"
    model_path = "../../nn/NNLowerDecayLR/20.pkl"

    # bins for moisture and lower tropospheric stability
    moisture_bins = np.arange(15)*2
    lts_bins = np.r_[7.5:17.5:.5]

    # load data
    tropics = subtropical_data()
    model = torch.load(model_path)

    # compute averages
    bin_averages = groupby_2d(tropics, lambda x: x.mean('gridcell'), lts_bins, moisture_bins)
    counts = groupby_2d(tropics, lambda x: x.gridcell.count(), lts_bins, moisture_bins)

    # compute nn output and diagnostics within bins
    mass = tropics.layer_mass[0]
    output = compute_nn(model, bin_averages, ['path_bins', 'lts_bins'])
    p_minus_e = -integrate_q2(output.QT, mass).rename('net_precipitation_nn')
    heating = integrate_q1(output.SLI, mass).rename('net_heating_nn')
    
    
    # form into one dataset
    return xr.merge([
        output.rename({
            'QT': 'Q2NN',
            'SLI': 'Q1NN'
        }),
        p_minus_e,
        heating,
        heating_weighted_height(output.SLI, mass),
        bin_averages,
        counts.rename('count'),
        -integrate_q2(bin_averages.Q2, mass).rename('net_precipitation_src'),
        integrate_q1(bin_averages.Q1, mass).rename('net_heating_src'),
        net_precipitation_from_prec_evap(bin_averages)
        .rename('net_precipitation')
    ])
    
    
def interval_coordinates_to_midpoint(ds):
    new_coords = {}
    coords = ds.coords
    
    for dim, coord in coords.items():
        if dim.endswith('bins'):
            new_coords[dim] = np.vectorize(lambda x: x.mid)(coord)
    return ds.assign_coords(**new_coords)
    
    
if __name__ == '__main__':
    import sys
    binned = get_data()
    binned.pipe(interval_coordinates_to_midpoint).to_netcdf(sys.argv[1])
