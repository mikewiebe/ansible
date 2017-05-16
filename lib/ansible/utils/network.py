def get_implementation_module(network_os, platform_agnostic_module):
    return network_os + '_' + platform_agnostic_module.partition('_')[2]
