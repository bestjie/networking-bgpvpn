# Copyright (c) 2015 Orange.
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

import sqlalchemy as sa

from oslo_utils import uuidutils

from neutron.common import exceptions as q_exc
from neutron.db import common_db_mixin
from neutron.db import model_base
from neutron.db import models_v2
from oslo_log import log
from sqlalchemy.orm import exc

LOG = log.getLogger(__name__)


class BGPVPNConnection(model_base.BASEV2,
                       models_v2.HasId,
                       models_v2.HasTenant):
    """Represents a BGPVPNConnection Object."""
    __tablename__ = 'bgpvpn_connections'
    name = sa.Column(sa.String(255))
    type = sa.Column(sa.Enum("l2", "l3",
                             name="bgpvpn_type"),
                     nullable=False)
    route_targets = sa.Column(sa.String(255), nullable=False)
    import_targets = sa.Column(sa.String(255), nullable=False)
    export_targets = sa.Column(sa.String(255), nullable=False)
    route_distinguishers = sa.Column(sa.String(255), nullable=False)
    auto_aggregate = sa.Column(sa.Boolean(), nullable=False)
    network_id = sa.Column(sa.String(36))


class BGPVPNConnectionNotFound(q_exc.NotFound):
    message = _("BgpVpnConnection %(conn_id)s could not be found")


class BGPVPNConnectionMissingRouteTarget(q_exc.BadRequest):
    message = _("BgpVpnConnection could not be created. Missing one of"
                " route_targets, import_targets or export_targets attribute")


class BGPVPNNetworkInUse(q_exc.NetworkInUse):
    message = _("Unable to complete operation on network %(network_id)s. "
                "There are one or more BGP VPN connections associated"
                " to the network.")


class BGPVPNPluginDb(common_db_mixin.CommonDbMixin):
    """BGP VPN service plugin database class using SQLAlchemy models."""

    def _rtrd_list2str(self, list):
        """Format Route Target list to string"""
        if not list:
            return ''

        return ','.join(list)

    def _rtrd_str2list(self, str):
        """Format Route Target string to list"""
        if not str:
            return []

        return str.split(',')

    def _get_bgpvpn_connections_for_tenant(self, session, tenant_id, fields):
        try:
            qry = session.query(BGPVPNConnection)
            bgpvpn_connections = qry.filter_by(tenant_id=tenant_id)
        except exc.NoResultFound:
            return

        return [self._make_bgpvpn_connection_dict(bvc, fields=fields)
                for bvc in bgpvpn_connections]

    def _make_bgpvpn_connection_dict(self,
                                     bgpvpn_connection,
                                     fields=None):
        res = {
            'id': bgpvpn_connection['id'],
            'tenant_id': bgpvpn_connection['tenant_id'],
            'network_id': bgpvpn_connection['network_id'],
            'name': bgpvpn_connection['name'],
            'type': bgpvpn_connection['type'],
            'route_targets':
                self._rtrd_str2list(bgpvpn_connection['route_targets']),
            'import_targets':
                self._rtrd_str2list(bgpvpn_connection['import_targets']),
            'export_targets':
                self._rtrd_str2list(bgpvpn_connection['export_targets']),
            'route_distinguishers':
                self._rtrd_str2list(bgpvpn_connection['route_distinguishers']),
            'auto_aggregate': bgpvpn_connection['auto_aggregate']
        }
        return self._fields(res, fields)

    def create_bgpvpn_connection(self, context, bgpvpn_connection):
        bgpvpn_conn = bgpvpn_connection['bgpvpn_connection']

        # Check that route_targets is not empty
        if (not bgpvpn_conn['route_targets']):
            raise BGPVPNConnectionMissingRouteTarget
        else:
            rt = self._rtrd_list2str(bgpvpn_conn['route_targets'])
            i_rt = self._rtrd_list2str(bgpvpn_conn['import_targets'])
            e_rt = self._rtrd_list2str(bgpvpn_conn['export_targets'])
            rd = self._rtrd_list2str(
                bgpvpn_conn.get('route_distinguishers', ''))

        tenant_id = self._get_tenant_id_for_create(context, bgpvpn_conn)

        with context.session.begin(subtransactions=True):
            bgpvpn_conn_db = BGPVPNConnection(
                id=uuidutils.generate_uuid(),
                tenant_id=tenant_id,
                name=bgpvpn_conn['name'],
                type=bgpvpn_conn['type'],
                route_targets=rt,
                import_targets=i_rt,
                export_targets=e_rt,
                route_distinguishers=rd,
                network_id=bgpvpn_conn['network_id'],
                auto_aggregate=bgpvpn_conn['auto_aggregate']
            )
            context.session.add(bgpvpn_conn_db)

        return self._make_bgpvpn_connection_dict(bgpvpn_conn_db)

    def get_bgpvpn_connections(self, context, filters=None, fields=None):
        return self._get_collection(context, BGPVPNConnection,
                                    self._make_bgpvpn_connection_dict,
                                    filters=filters, fields=fields)

    def _get_bgpvpn_connection(self, context, id):
        try:
            return self._get_by_id(context, BGPVPNConnection, id)
        except exc.NoResultFound:
            raise BGPVPNConnectionNotFound(conn_id=id)

    def get_bgpvpn_connection(self, context, id, fields=None):
        bgpvpn_connection_db = self._get_bgpvpn_connection(context, id)
        LOG.debug("get_bgpvpn_connection called with fields = %s" % fields)

        return self._make_bgpvpn_connection_dict(bgpvpn_connection_db, fields)

    def update_bgpvpn_connection(self, context, id, bgpvpn_connection):
        bgpvpn_conn = bgpvpn_connection['bgpvpn_connection']
        fields = None

        LOG.debug("update_bgpvpn_connection called with %s for %s"
                  % (bgpvpn_connection, id))

        with context.session.begin(subtransactions=True):
            bgpvpn_connection_db = self._get_bgpvpn_connection(context, id)

            if bgpvpn_conn:
                # Format Route Target lists to string
                if 'route_targets' in bgpvpn_conn:
                    rt = self._rtrd_list2str(bgpvpn_conn['route_targets'])
                    bgpvpn_conn['route_targets'] = rt
                if 'import_targets' in bgpvpn_conn:
                    i_rt = self._rtrd_list2str(bgpvpn_conn['import_targets'])
                    bgpvpn_conn['import_targets'] = i_rt
                if 'export_targets' in bgpvpn_conn:
                    e_rt = self._rtrd_list2str(bgpvpn_conn['export_targets'])
                    bgpvpn_conn['export_targets'] = e_rt
                if 'route_distinguishers' in bgpvpn_conn:
                    rd = self._rtrd_list2str(
                        bgpvpn_conn['route_distinguishers'])
                    bgpvpn_conn['route_distinguishers'] = rd

                bgpvpn_connection_db.update(bgpvpn_conn)

        return self._make_bgpvpn_connection_dict(bgpvpn_connection_db, fields)

    def delete_bgpvpn_connection(self, context, id):
        with context.session.begin(subtransactions=True):
            bgpvpn_connection_db = self._get_by_id(context,
                                                   BGPVPNConnection,
                                                   id)

            context.session.delete(bgpvpn_connection_db)

        return bgpvpn_connection_db

    def find_bgpvpn_connections_for_network(self, context, network_id):
        LOG.debug("get_bgpvpn_connections_for_network() called for "
                  "network %s" %
                  network_id)

        try:
            bgpvpn_connections = (context.session.query(BGPVPNConnection).
                                  filter(BGPVPNConnection.network_id ==
                                         network_id).
                                  all())
        except exc.NoResultFound:
            return

        return [self._make_bgpvpn_connection_dict(bvc)
                for bvc in bgpvpn_connections]