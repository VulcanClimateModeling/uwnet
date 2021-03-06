import xarray as xr
from os.path import join, abspath
import json

import click

from .case import InitialConditionCase, get_ngqaua_ic, default_parameters

NGAQUA_ROOT = "/Users/noah/Data/2018-05-30-NG_5120x2560x34_4km_10s_QOBS_EQX"

resolution_help = (
    "Resolution of model to use. Only '128x64x34' and '512x256x34' are "
    "currently supported."""
)


def save_as_json(config, path):
    with open(path, "w") as f:
        json.dump(config, f)

@click.command()
@click.argument('path')
@click.option(
    '-nn',
    '--neural-network',
    type=click.Path(),
    help='use the neural network in this pickled model file.')
@click.option(
    '-sk',
    '--sklearn-generic',
    type=click.Path(),
    help='pickled model file for generic sklearn_generic regressor'
)
@click.option(
    '--noise',
    type=click.Path(),
    help='A noise model stored in a pickle file.')
@click.option('-ic', '--initial-condition', type=click.Path(), default=None)
@click.option('-n', '--ngaqua-root', type=click.Path(), default=NGAQUA_ROOT)
@click.option('-t', type=int, default=0)
@click.option('-p', '--parameters', type=click.Path(), default=None)
@click.option('-d', '--debug',  is_flag=True)
@click.option('-s', '--sam-src', type=str, default='/opt/sam')
@click.option('-r', '--run-data', type=str, default='/opt/sam/RUNDATA')
@click.option('--resolution', type=str, default='128x64x34', help=resolution_help)
def main(path,
         sklearn_generic,
         neural_network,
         noise,
         initial_condition,
         ngaqua_root,
         t,
         parameters,
         debug,
         sam_src,
         run_data,
         resolution):
    """Create SAM case directory for an NGAqua initial value problem and optionally
    run the model with docker.

    """

    model_run_path = "model.pkl"

    if parameters:
        parameters = json.load(open(parameters))
    else:
        parameters = default_parameters()

    python_config = {'models': []}

    if initial_condition is None:
        initial_condition = get_ngqaua_ic(ngaqua_root, t)
    else:
        initial_condition = xr.open_dataset(initial_condition)

    case = InitialConditionCase(path=path, ic=initial_condition,
                                sam_src=sam_src, run_data=run_data,
                                prm=parameters, resolution=resolution)

    # configure neural network run
    python_config_path = join(path, "python_config.json")
    if neural_network:
        case.prm['python']['dopython'] = False

        # setup the neural network
        case.prm['python'].update(
            dict(
                dopython=True,
                usepython=True,
                function_name='call_neural_network',
                module_name='uwnet.ml_models.nn.sam_interface'))

        case.mkdir()

        print(f"Copying neural networks to model directory")
        case.add(neural_network, model_run_path)

    if sklearn_generic:
        case.prm['python']['dopython'] = False
        case.prm['python'].update(
            dict(
                dopython=True,
                usepython=True,
                function_name='call_sklearn_model',
                module_name='uwnet.ml_models.sklearn_generic.sam_interface'))

        print(f"Copying model to run directory")
        case.mkdir()
        case.add(sklearn_generic, model_run_path)
        python_config['models'].append(
            {"type": "sklearn_generic", "path": model_run_path})

    if noise:
        noise_model_path = "noise.pkl"
        case.add(noise, noise_model_path)
        python_config['models'].append(
            {"type": "cf", "path": noise_model_path})

    if 'nudging' in parameters:
        config = parameters['nudging']
        config['ngaqua'] = abspath('data/processed/training/noBlur.nc')
        config['type'] = 'nudging'
        python_config['models'].append(config)

    if debug:
        case.prm['parameters'].update({
            'nsave3d': 20,
            'nsave2d': 20,
            'nstat': 20,
            'nstop': 120,
        })

    case.save()
    save_as_json(python_config, python_config_path)



if __name__ == '__main__':
    main()
