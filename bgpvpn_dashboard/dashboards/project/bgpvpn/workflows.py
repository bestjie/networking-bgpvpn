# Copyright (c) 2016 Orange.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import logging

from django.utils.translation import ugettext_lazy as _
from horizon import exceptions
from horizon import forms
from horizon import workflows
from openstack_dashboard import api

LOG = logging.getLogger(__name__)

from bgpvpn_dashboard.api import bgpvpn as bgpvpn_api


class UpdateAssociations(workflows.MembershipAction):
    def __init__(self, request, resource_type, *args, **kwargs):
        super(UpdateAssociations, self).__init__(request,
                                                 *args,
                                                 **kwargs)
        err_msg = _('Something went wrong when retrieving the list of '
                    'associations')
        if resource_type == 'router':
            err_msg = _('Unable to retrieve list of routers. '
                        'Please try again later.')
        elif resource_type == 'network':
            err_msg = _('Unable to retrieve list of networks. '
                        'Please try again later.')
        context = args[0]

        default_role_field_name = self.get_default_role_field_name()
        self.fields[default_role_field_name] = forms.CharField(required=False)
        self.fields[default_role_field_name].initial = 'member'

        field_name = self.get_member_field_name('member')
        self.fields[field_name] = forms.MultipleChoiceField(required=False)

        all_resources = self._get_resources(request, context, resource_type,
                                            err_msg)

        resources_list = [(resource.id, resource.name_or_id)
                          for resource in all_resources]

        self.fields[field_name].choices = resources_list

        bgpvpn_id = context.get('bgpvpn_id')

        try:
            if bgpvpn_id:
                associations = []
                list_method = getattr(bgpvpn_api, '%s_association_list' %
                                      resource_type)
                associations = [
                    getattr(association, '%s_id' %
                            resource_type) for association in
                    list_method(request, bgpvpn_id)
                    ]

        except Exception:
            exceptions.handle(request, err_msg)

        self.fields[field_name].initial = associations

    def _get_resources(self, request, context, resource_type, err_msg):
        """Get list of available resources."""
        # when an admin user uses the project panel BGPVPN, there is no
        # tenant_id in context because bgpvpn_get doesn't return it
        if request.user.is_superuser and context.get('tenant_id'):
            tenant_id = context.get('tenant_id')
        else:
            tenant_id = self.request.user.tenant_id
        try:
            if resource_type == 'router':
                return api.neutron.router_list(request, tenant_id=tenant_id)
            elif resource_type == 'network':
                return api.neutron.network_list_for_tenant(request, tenant_id)
            else:
                raise Exception(
                    _('Resource type not supported: %s') % resource_type)
        except Exception:
            exceptions.handle(request, err_msg % resource_type)


class UpdateBgpVpnRoutersAction(UpdateAssociations):
    def __init__(self, request, *args, **kwargs):
        super(UpdateBgpVpnRoutersAction, self).__init__(request,
                                                        'router',
                                                        *args,
                                                        **kwargs)

    class Meta(object):
        name = _("Router Associations")
        slug = "update_bgpvpn_router"


class UpdateBgpVpnRouters(workflows.UpdateMembersStep):
    action_class = UpdateBgpVpnRoutersAction
    help_text = _("Select the routers to be associated.")
    available_list_title = _("All Routers")
    members_list_title = _("Selected Routers")
    no_available_text = _("No router found.")
    no_members_text = _("No router selected.")
    show_roles = False
    depends_on = ("bgpvpn_id", "name")
    contributes = ("routers_association",)

    def contribute(self, data, context):
        if data:
            member_field_name = self.get_member_field_name('member')
            context['routers_association'] = data.get(member_field_name, [])
        return context


class UpdateBgpVpnNetworksAction(UpdateAssociations):
    def __init__(self, request, *args, **kwargs):
        super(UpdateBgpVpnNetworksAction, self).__init__(request,
                                                         'network',
                                                         *args,
                                                         **kwargs)

    class Meta(object):
        name = _("Network Associations")
        slug = "update_bgpvpn_network"


class UpdateBgpVpnNetworks(workflows.UpdateMembersStep):
    action_class = UpdateBgpVpnNetworksAction
    help_text = _("Select the networks to be associated.")
    available_list_title = _("All Networks")
    members_list_title = _("Selected Networks")
    no_available_text = _("No network found.")
    no_members_text = _("No network selected.")
    show_roles = False
    depends_on = ("bgpvpn_id", "name")
    contributes = ("networks_association",)

    def contribute(self, data, context):
        if data:
            member_field_name = self.get_member_field_name('member')
            context['networks_association'] = data.get(member_field_name, [])
        return context


class UpdateBgpVpnAssociations(workflows.Workflow):
    slug = "update_bgpvpn_associations"
    name = _("Edit BGPVPN associations")
    finalize_button_name = _("Save")
    success_message = _('Modified BGPVPN associations "%s".')
    failure_message = _('Unable to modify BGPVPN associations "%s".')
    success_url = "horizon:project:bgpvpn:index"
    default_steps = (UpdateBgpVpnNetworks,
                     UpdateBgpVpnRouters)

    def format_status_message(self, message):
        return message % self.context['name']

    def _handle_type(self, request, data, association_type):
        list_method = getattr(bgpvpn_api,
                              '%s_association_list' % association_type)
        associations = data["%ss_association" % association_type]
        error_msg = 'Unable to retrieve associations'
        try:
            old_associations = [
                getattr(association,
                        '%s_id' % association_type) for association in
                list_method(request, data['bgpvpn_id'])]
        except Exception:
            if association_type == 'router':
                error_msg = _('Unable to retrieve router associations')
            elif association_type == 'network':
                error_msg = _('Unable to retrieve network associations')
            exceptions.handle(request, error_msg)
            raise

        to_remove_associations = list(set(old_associations) -
                                      set(associations))
        to_add_associations = list(set(associations) -
                                   set(old_associations))

        # If new resource added to the list
        if len(to_add_associations) > 0:
            for resource in to_add_associations:
                error_msg = _('Unable to associate resource %s') % resource
                try:
                    create_asso = getattr(bgpvpn_api,
                                          '%s_association_create' %
                                          association_type)
                    params = self._set_params(data, association_type, resource)
                    create_asso(request,
                                data['bgpvpn_id'],
                                **params)
                except Exception as e:
                    if association_type == 'router':
                        error_msg = _(
                            'Unable to associate router {}: {}').format(
                            resource, str(e))
                    elif association_type == 'network':
                        error_msg = _(
                            'Unable to associate network {}: {}').format(
                            resource, str(e))
                    exceptions.handle(request, error_msg)
                    raise

        # If resource has been deleted from the list
        if len(to_remove_associations) > 0:
            for resource in to_remove_associations:
                try:
                    list_method = getattr(bgpvpn_api,
                                          '%s_association_list' %
                                          association_type)
                    asso_list = list_method(request, data['bgpvpn_id'])
                    for association in asso_list:
                        if getattr(association,
                                   '%s_id' % association_type) == resource:
                            delete_method = getattr(bgpvpn_api,
                                                    '%s_association_delete' %
                                                    association_type)
                            delete_method(request,
                                          association.id, data['bgpvpn_id'])
                except Exception:
                    if association_type == 'router':
                        error_msg = _('Unable to disassociate router')
                    elif association_type == 'network':
                        error_msg = _('Unable to disassociate network')
                    exceptions.handle(request, error_msg)
                    raise

    def _set_params(self, data, association_type, resource):
        params = dict()
        params['%s_id' % association_type] = resource
        return params

    def handle(self, request, data):
        action = False
        try:
            if 'networks_association' in data:
                self._handle_type(request, data, 'network')
                action = True
            if 'routers_association' in data:
                self._handle_type(request, data, 'router')
                action = True
            if not action:
                raise Exception(_('Associations type is not supported'))
        except Exception:
            return False
        return True


class AddRouterParametersInfoAction(workflows.Action):

    advertise_extra_routes = forms.BooleanField(
        label=_("Advertise Extra Routes"),
        initial=True,
        required=False,
        help_text="Boolean flag controlling whether or not the routes "
                  "specified in the routes attribute of the router will be "
                  "advertised to the BGPVPN (default: true).")

    class Meta(object):
        name = _("Optional Parameters")
        slug = "add_router_parameters"

    def __init__(self, request, context, *args, **kwargs):
        super(AddRouterParametersInfoAction, self).__init__(
            request, context, *args, **kwargs)
        if 'with_parameters' in context:
            self.fields['with_parameters'] = forms.BooleanField(
                initial=context['with_parameters'],
                required=False,
                widget=forms.HiddenInput()
            )


class CreateRouterAssociationInfoAction(workflows.Action):

    router_resource = forms.ChoiceField(
        label=_("Associate Router"),
        widget=forms.ThemableSelectWidget(
            data_attrs=('name', 'id'),
            transform=lambda x: "%s" % x.name_or_id))

    class Meta(object):
        name = _("Create Association")
        help_text = _("Create a new router association.")
        slug = "create_router_association"

    def __init__(self, request, context, *args, **kwargs):
        super(CreateRouterAssociationInfoAction, self).__init__(
            request, context, *args, **kwargs)

        # when an admin user uses the project panel BGPVPN, there is no
        # tenant_id in context because bgpvpn_get doesn't return it
        if request.user.is_superuser and context.get("project_id"):
            tenant_id = context.get("project_id")
        else:
            tenant_id = self.request.user.tenant_id

        try:
            routers = api.neutron.router_list(request, tenant_id=tenant_id)
            if routers:
                choices = [('', _("Choose a router"))] + [(r.id, r) for r in
                                                          routers]
                self.fields['router_resource'].choices = choices
            else:
                self.fields['router_resource'].choices = [('', _("No router"))]
        except Exception:
            exceptions.handle(request, _("Unable to retrieve routers"))

        if api.neutron.is_extension_supported(request,
                                              'bgpvpn-routes-control'):
            self.fields['with_parameters'] = forms.BooleanField(
                label=_("Optional parameters"),
                initial=False,
                required=False,
                widget=forms.CheckboxInput(attrs={
                    'class': 'switchable',
                    'data-hide-tab': 'router_association__'
                                     'add_router_parameters',
                    'data-hide-on-checked': 'false'
                }))


class AddRouterParametersInfo(workflows.Step):
    action_class = AddRouterParametersInfoAction
    depends_on = ("bgpvpn_id", "name")
    contributes = ("advertise_extra_routes",)


class CreateRouterAssociationInfo(workflows.Step):
    action_class = CreateRouterAssociationInfoAction
    contributes = ("router_resource", "with_parameters")


class RouterAssociation(workflows.Workflow):
    slug = "router_association"
    name = _("Associate a BGPVPN to a Router")
    finalize_button_name = _("Create")
    success_message = _('Router association with "%s" created.')
    failure_message = _('Unable to create a router association with "%s".')
    success_url = "horizon:project:bgpvpn:index"
    default_steps = (CreateRouterAssociationInfo,
                     AddRouterParametersInfo)
    wizard = True

    def format_status_message(self, message):
        name = self.context['name'] or self.context['bgpvpn_id']
        return message % name

    def handle(self, request, context):
        bgpvpn_id = context['bgpvpn_id']
        router_id = context["router_resource"]
        msg_error = _("Unable to associate router %s") % router_id
        try:
            router_association = bgpvpn_api.router_association_create(
                request, bgpvpn_id, router_id=router_id)
        except Exception as e:
            exceptions.handle(request, msg_error + ": %s" % str(e))
            return False
        if not context["with_parameters"]:
            return True
        asso_id = router_association['router_association']['id']
        try:
            bgpvpn_api.router_association_update(
                request, bgpvpn_id, asso_id,
                advertise_extra_routes=context['advertise_extra_routes'])
            return True
        except exceptions as e:
            bgpvpn_api.router_association_delete(request, asso_id, bgpvpn_id)
            exceptions.handle(request, msg_error + ": %s" % str(e))
            return False
