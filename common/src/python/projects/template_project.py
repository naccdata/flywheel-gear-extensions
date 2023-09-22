"""Defines the process for copying a set of gear rules from a source project,
the template, to other projects.

Based on code written by David Parker, davidparker@flywheel.io
"""
import logging
from string import Template
from typing import Dict, List, Optional

import flywheel
from flywheel import (DataView, FileEntry, FixedInput, GearRule, GearRuleInput,
                      ViewerApp)
from flywheel_adaptor.flywheel_proxy import FlywheelProxy
from flywheel_adaptor.project_adaptor import ProjectAdaptor

log = logging.getLogger()


# pylint: disable=(too-few-public-methods)
class TemplateProject:
    """Function object to copy gear rules and associated files from a source
    template project to other projects."""

    def __init__(self, *, proxy: FlywheelProxy, project: flywheel.Project):
        """Initializes the template object.

        Args:
           proxy: the proxy object for the flywheel instance
           project: the source (template) project
        """
        self.__fw = proxy
        self.__source_project = project
        self.__rules: List[GearRule] = []
        self.__dataviews: List[DataView] = []
        self.__apps: List[ViewerApp] = []

    def copy_to(self,
                destination: ProjectAdaptor,
                *,
                value_map: Optional[Dict[str, str]] = None) -> None:
        """Copies all gear rules from the source project of the template to the
        destination project.

        Uses memoization, so loads the rules from the source project once.

        Args:
          destination: project to copy to
          value_map: optional map for substitutions for description template
        """
        self.copy_rules(destination)
        self.copy_users(destination)
        if value_map:
            self.copy_description(destination=destination, values=value_map)
        self.copy_apps(destination)

    def copy_apps(self, destination: ProjectAdaptor) -> None:
        """Performs copy of viewer apps to the destination.

        Replaces any existing apps in the destination project.

        Args:
          destination: the destination project
        """
        if not self.__apps:
            log.info('loading apps for template project %s',
                     self.__source_project.label)
            self.__apps = self.__fw.get_project_apps(self.__source_project)
            if not self.__apps:
                log.warning('template %s has no apps, skipping',
                            self.__source_project.label)
                return

        assert self.__apps
        log.info('copying apps from template %s to %s/%s',
                 self.__source_project.label, destination.group,
                 destination.label)
        destination.set_apps(self.__apps)

    def copy_rules(self, destination: ProjectAdaptor) -> None:
        """Performs copy of gear rules to destination.

        Removes any conflicting rules from the destination.

        Args:
          destination: the destination project
        """
        if not self.__rules:
            log.info('loading rules for template project %s',
                     self.__source_project.label)
            self.__rules = self.__fw.get_project_gear_rules(
                self.__source_project)
            if not self.__rules:
                log.warning('template %s has no rules, skipping',
                            self.__source_project.label)
                return

        assert self.__rules

        self.__clean_up_rules(destination)

        for rule in self.__rules:
            log.info('copying rule %s to project %s', rule.name,
                     destination.label)
            fixed_inputs = self.__map_fixed_inputs(inputs=rule.fixed_inputs,
                                                   destination=destination)
            gear_rule_input = self.__create_gear_rule_input(
                rule=rule, fixed_inputs=fixed_inputs)
            destination.add_gear_rule(rule_input=gear_rule_input)

    def copy_users(self, destination: ProjectAdaptor) -> None:
        """Copies users from this project to the destination.

        Args:
          destination: the destination project
        """
        role_assignments = self.__source_project.permissions
        for role_assignment in role_assignments:
            destination.add_user_roles(role_assignment)

    def copy_description(self, *, destination: ProjectAdaptor,
                         values: Dict[str, str]) -> None:
        """Copies description from this project to the destination.

        Args:
          destination: the destination project
          values: value map for substitutions into description template
        """
        template_text = self.__source_project.description
        if not template_text:
            log.info('no description found in %s project',
                     self.__source_project.label)
            return

        template = Template(template_text)
        description = template.substitute(values)
        destination.set_description(description)

    def copy_dataviews(self, *, destination: ProjectAdaptor) -> None:
        """Copies the dataviews from this project to the destination.

        Args:
          destination: the destination project
        """
        if not self.__dataviews:
            log.info('copying dataviews for the template %s',
                     self.__source_project.label)
            self.__dataviews = self.__fw.get_dataviews(self.__source_project)
            if not self.__dataviews:
                log.warning('template %s has no dataviews',
                            self.__source_project.label)
                return

        # TODO: cleanup dataviews?

        for dataview in self.__dataviews:
            destination_dataview = destination.get_dataview(dataview.label)
            if destination_dataview:
                if self.__equal_views(destination_dataview, dataview):
                    return
                # TODO: decide whether to modify instead?
                self.__fw.delete_dataview(destination_dataview)

            destination.add_dataview(dataview)

    def __clean_up_rules(self, destination: ProjectAdaptor) -> None:
        """Remove any gear rules from destination that are not in this
        template.

        Args:
          destination: the detination project
        """
        destination_rules = destination.get_gear_rules()
        if not destination_rules:
            return

        assert self.__rules
        template_rulenames = [rule.name for rule in self.__rules]
        for rule in destination_rules:
            if rule.name not in template_rulenames:
                log.info('removing rule %s, not in template %s', rule.name,
                         self.__source_project.label)
                destination.remove_gear_rule(rule=rule)

    def __map_fixed_inputs(self, *, inputs: List[FixedInput],
                           destination: ProjectAdaptor) -> List[FixedInput]:
        """Maps the given fixed inputs to inputs for the destination project.

        Args:
          rule: the gear rule
          destination: the destination project
        Returns:
          list of inputs in destination project
        """
        dest_inputs = []
        for fixed_input in inputs:
            file_object = self.__source_project.get_file(fixed_input.name)

            if not self.__same_file_exists(file_object, destination):
                self.__copy_file(file_object, destination)

            dest_inputs.append(
                FixedInput(id=destination.id,
                           input=fixed_input.input,
                           name=fixed_input.name,
                           type=fixed_input.type,
                           version=fixed_input.version))

        return dest_inputs

    @staticmethod
    def __copy_file(file: FileEntry, destination: ProjectAdaptor) -> None:
        """Copies the file to the destination project.

        Args:
          file: the file entry for the file
          destination: the destination project
        """
        log.info("copying file %s to %s", file.name, destination.label)
        file_spec = flywheel.FileSpec(file.name, file.read(), file.mimetype)
        destination.upload_file(file_spec)

    @staticmethod
    def __same_file_exists(file: FileEntry, project: ProjectAdaptor) -> bool:
        """Determines whether the destination project has a file with the same
        name and hash value as the given file.

        Args:
          file: the file
          project: the project to check whether a matching file exists
        Returns:
            True if the project has a file with same name and hash.
            False otherwise.
        """
        dest_file = project.get_file(file.name)
        if not dest_file:
            log.debug("No File %s on destination project %s, uploading",
                      file.name, project.label)
            return False

        if dest_file.hash == file.hash:
            log.debug(
                "File %s on destination project %s matches hash of original "
                "file, no changes", file.name, project.label)
            return True

        log.debug(
            "File %s on destination project %s does not match hash of "
            "original file, updating", file.name, project.label)
        return False

    @staticmethod
    def __create_gear_rule_input(
            *, rule: GearRule,
            fixed_inputs: List[FixedInput]) -> GearRuleInput:
        """Creates a GearRuleInput object for the rule using the fixed inputs.

        Args:
          rule: the gear rule
          fixed_inputs: the fixed inputs to add to the rule
        Returns:
          the new gear rule input object
        """

        return GearRuleInput(
            project_id=rule.project_id,
            gear_id=rule.gear_id,
            role_id=rule.role_id,
            name=rule.name,
            config=rule.config,
            fixed_inputs=fixed_inputs,
            auto_update=rule.auto_update,
            any=rule.any,
            all=rule.all,
            _not=rule._not,  # pylint: disable=(protected-access)
            disabled=rule.disabled,
            compute_provider_id=rule.compute_provider_id,
            triggering_input=rule.triggering_input)

    @staticmethod
    def __equal_views(first: DataView, second: DataView) -> bool:
        """Checks whether the first and second dataviews are equivalent.

        Checks properties: columns, label, sort, error_colum, file_spec,
        filter, group_by, include_ids, include_labels, missing_data_strategy

        Args:
          first: a dataview
          second: a dataview
        Returns:
          True if views are equivalent on listed properties, False otherwise
        """
        properties = [
            "columns", "label", "sort", "error_column", "file_spec", "filter",
            "group_by", "include_ids", "include_labels",
            "missing_data_strategy"
        ]
        for view_property in properties:
            if first.get(view_property) != second.get(view_property):
                return False

        return True
