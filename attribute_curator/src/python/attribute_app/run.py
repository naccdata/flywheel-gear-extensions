"""ADD DETAIL HERE"""

import logging
import sys
from flywheel_adaptor.flywheel_proxy import FlywheelProxy

from flywheel_gear_toolkit import GearToolkitContext
from inputs.context_parser import parse_config
from inputs.api_key import get_api_key
from inputs.parameter_store import get_parameter_store
from inputs.yaml import get_object_list
from attribute_app.main import run


logging.basicConfig(stream=sys.stdout, level=logging.INFO)
log = logging.getLogger(__name__)

def main():
    """Describe gear detail here"""

    filename = 'attribute_file'
    with GearToolkitContext() as gear_context:
        gear_context.init_logging()
        context_args = parse_config(gear_context=gear_context,
                                    filename=filename)
        #
        # get argument values from context_args
        #
        admin_group_name = context_args['admin_group']
        dry_run = context_args['dry_run']
        new_only = context_args['new_only']
        input_file = context_args[filename] # gets the file name

        # uses api_key passed to gear
        client = gear_context.client
        # will need different code if want client using the bot API key

    if not client:
        log.error('No Flywheel connection. Check API key configuration.')
        sys.exit(1)

    # assumes input file is a YAML file
    object_list = get_object_list(input_file)
    if not object_list:
        log.error('No objects read from input')
        sys.exit(1)

    flywheel_proxy = FlywheelProxy(client=client, dry_run=dry_run)

    run(proxy=flywheel_proxy,
        object_list=object_list,
        new_only=new_only)

    if __name__ == "__main__":
        main()
