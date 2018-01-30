"""Data loading and preprocessing routines
"""
import numpy as np
import torch
import xarray as xr
from sklearn.externals import joblib
from torch.autograd import Variable

from lib.util import compute_weighted_scale, scales_to_np, weights_to_np

from toolz import pipe, merge, reduce, curry
from toolz.curried import valmap

from collections import Mapping, Iterable


def stacked_data(X):

    sl = np.asarray(X['sl'])
    qt = np.asarray(X['qt'])

    # do not use the moisture field above 200 hPA
    # this is the top 14 grid points for NGAqua
    # ntop = -14
    # qt = qt[..., :ntop].astype(float)
    # sl = sl[..., :ntop].astype(float)

    return np.concatenate((sl, qt), axis=-1)

    return X


def pad_along_axis(x, pad_width, mode, axis):
    pad_widths = [(0, 0)]*x.ndim
    pad_widths[axis] = pad_width
    return np.pad(x, pad_widths, mode)


def _stacked_to_dict(X):
    """Inverse operation of stacked_data """

    nf = X.shape[-1]
    # nz + nz - 14 = nf
    # nz = (nf+14)//2
    nz = nf//2

    sl = X[...,:nz]
    qt = X[...,nz:]

    # qt = pad_along_axis(qt, (0,14), 'constant', -1)

    return {'sl': sl, 'qt': qt}


def stacked_to_xr(X, **kwargs):
    d = _stacked_to_dict(X)
    data_vars = {key: xr.DataArray(val, **kwargs) for key, val in d.items()}
    return xr.Dataset(data_vars)


def _dataset_to_dict(ds: xr.Dataset):
    return {key: ds[key].values for key in ds.data_vars}


def _wrap_args(args, cuda=False, to_numpy=False):

    wrap = curry(_wrap_args, cuda=cuda, to_numpy=to_numpy)
    if isinstance(args, tuple):
        return tuple(map(wrap, args))
    elif isinstance(args, Mapping):
        return valmap(wrap, args)
    elif isinstance(args, xr.Dataset):
        return {key: wrap(args[key]) for key in args.data_vars}
    elif isinstance(args, xr.DataArray):
        x = args
        # transpose data into correct order
        x = x.transpose('time', 'batch', 'z')
        # turn it into a pytorch variable
        return Variable(torch.FloatTensor(x.values))
    elif isinstance(args, Variable):
        if to_numpy:
            return args.data.cpu().numpy()
        else:
            return args


def wrap(torch_model):
    def fun(*args):
        torch_args = _wrap_args(args)

        y = torch_model(*torch_args)
        y  = _wrap_args(y, to_numpy=True)

        return y

    return fun


def prepare_array(x):
    output_dims = [dim for dim in ['time', 'y', 'x', 'z']
                   if dim in x.dims]
    return x.transpose(*output_dims).values

def prepare_data(inputs: xr.Dataset, forcings: xr.Dataset):

    w = inputs.w

    fields = ['sl', 'qt']

    weights = {key: w.values for key in fields}

    # compute scales
    sample_dims = set(['x', 'y', 'time']) & set(inputs.dims)
    scales = compute_weighted_scale(w, sample_dims=sample_dims,
                                    ds=inputs[fields])
    scales = {key: float(scales[key]) for key in fields}

    X = {key: prepare_array(inputs[key]) for key in inputs.data_vars}
    G = {key: prepare_array(forcings[key]) for key in forcings.data_vars}

    # return stacked data

    return {
        'X': X,
        'G': G,
        'scales': scales,
        'w': weights,
        'p': inputs.p.values,
        'z': inputs.z.values
    }
