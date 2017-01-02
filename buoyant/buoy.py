# -*- coding: utf-8 -*-
# Copyright 2014 Neil Freeman
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
from datetime import datetime
import csv
import re
from io import BytesIO, StringIO
from pytz import timezone
import requests


# Both take station as a GET argument.
OBS_ENDPOINT = "http://sdf.ndbc.noaa.gov/sos/server.php"
CAM_ENDPOINT = 'http://www.ndbc.noaa.gov/buoycam.php'

'''
request=GetObservation
service=SOS
version=1.0.0
offering=urn:ioos:station:wmo:41012
observedproperty=air_pressure_at_sea_level
responseformat=text/csv
eventtime=latest
'''

# lat, lon, datetime are assigned separately.
PROPERTIES = [
    'air_pressure_at_sea_level',
    'air_temperature',
    'currents',
    'sea_floor_depth_below_sea_surface',
    'sea_water_electrical_conductivity',
    'sea_water_salinity',
    'sea_water_temperature',
    'waves',
    'winds',
]


CURRENTS_PROPERTIES = [
    'bin',  # (count)
    'depth',  # (m)
    'direction_of_sea_water_velocity',  # (degree)
    'sea_water_speed',  # (c/s)
    'upward_sea_water_velocity',  # (c/s)
    'error_velocity',  # (c/s)
    'platform_orientation',  # (degree)
    'platform_pitch_angle',  # (degree)
    'platform_roll_angle',  # (degree)
    'sea_water_temperature',  # (C)
    'pct_good_3_beam',  # (%)
    'pct_good_4_beam',  # (%)
    'pct_rejected',  # (%)
    'pct_bad',  # (%)
    'echo_intensity_beam1',  # (count)
    'echo_intensity_beam2',  # (count)
    'echo_intensity_beam3',  # (count)
    'echo_intensity_beam4',  # (count)
    'correlation_magnitude_beam1',  # (count)
    'correlation_magnitude_beam2',  # (count)
    'correlation_magnitude_beam3',  # (count)
    'correlation_magnitude_beam4',  # (count)
    'quality_flags',
]


def _setup_ndbc_dt(dt):
    '''parse the kind of datetime we're likely to get'''
    d = datetime.strptime(dt[:-1], '%Y-%m-%dT%H:%M:%S')

    if dt[-1:] == 'Z':
        return timezone('utc').localize(d)
    else:
        return d


def parse_unit(prop, dictionary):
    matches = [k for k in dictionary.keys() if prop in k]
    try:
        value = dictionary[matches[0]]
        unit = re.search(r' \(([^)]+)\)', matches[0])

        if not unit:
            return value

        if not value:
            return None

        return Observation(value, unit.group(1))

    except IndexError:
        return None


def _currents(iterable):
    return [{prop: parse_unit(prop, row) for prop in CURRENTS_PROPERTIES} for row in iterable]


'''
Response looks like:
station_id,sensor_id,"latitude (degree)","longitude (degree)",date_time,"depth (m)","air_pressure_at_sea_level (hPa)"
urn:ioos:station:wmo:41012,urn:ioos:sensor:wmo:41012::baro1,30.04,-80.55,2014-02-19T12:50:00Z,0.00,1022.1
'''


class Buoy(object):

    '''Wrapper for the NDBC Buoy information mini-API'''

    __dict__ = {}
    params = {
        'request': 'GetObservation',
        'service': 'SOS',
        'version': '1.0.0',
        'responseformat': 'text/csv',
    }

    def __init__(self, bouyid):
        self.id = bouyid
        self.refresh()

    def refresh(self):
        self.__dict__ = {
            'lat': None,
            'lon': None,
            'datetime': None,
        }

    def _get(self, observation):
        return self.__dict__.setdefault(observation, self.fetch(observation))

    def fetch(self, observation):
        p = {
            'offering': 'urn:ioos:station:wmo:{}'.format(self.id),
            'observedproperty': observation,
            'eventtime': 'latest'
        }
        params = dict(self.params.items() + p.items())
        request = requests.get(OBS_ENDPOINT, params=params)

        try:
            reader = csv.DictReader(StringIO(request.text))

            if observation == 'currents':
                return _currents(reader)
            else:
                result = next(reader)

            if 'ows:ExceptionReport' in str(result):
                raise AttributeError(observation)

        except StopIteration:
            raise AttributeError(observation)

        self.__dict__['station_id'] = result.get('station_id')
        self.__dict__['sensor_id'] = result.get('sensor_id')
        try:
            self.__dict__['lon'] = float(result.get('longitude (degree)'))
            self.__dict__['lat'] = float(result.get('latitude (degree)'))
            self.__dict__['datetime'] = _setup_ndbc_dt(result.get('date_time'))

        except TypeError:
            self.__dict__['lon'], self.__dict__['lat'] = None, None
            self.__dict__['datetime'] = None

        self.__dict__['depth'] = parse_unit('depth', result)

        return parse_unit(observation, result)

    @property
    def air_pressure_at_sea_level(self):
        return self._get('air_pressure_at_sea_level')

    @property
    def air_temperature(self):
        return self._get('air_temperature')

    @property
    def currents(self):
        return self._get('currents')

    @property
    def sea_floor_depth_below_sea_surface(self):
        return self._get('sea_floor_depth_below_sea_surface')

    @property
    def sea_water_electrical_conductivity(self):
        return self._get('sea_water_electrical_conductivity')

    @property
    def sea_water_salinity(self):
        return self._get('sea_water_salinity')

    @property
    def sea_water_temperature(self):
        return self._get('sea_water_temperature')

    @property
    def waves(self):
        return self._get('waves')

    @property
    def winds(self):
        return self._get('winds')

    @property
    def image_url(self):
        return '{0}?station={id}'.format(CAM_ENDPOINT, id=self.id)

    def _write_img(self, handle):
        i = requests.get(CAM_ENDPOINT, params={'station': self.id})
        for chunk in i.iter_content():
            handle.write(chunk)

    @property
    def image(self):
        output = BytesIO()
        self._write_img(output)
        output.seek(0)

        return output

    def save_image(self, filename):
        with open(filename, 'wb') as f:
            self._write_img(f)

    @property
    def coords(self):
        return self.__dict__.get('lat'), self.__dict__.get('lon')

    @property
    def depth(self):
        return self.__dict__.get('depth')

    @property
    def datetime(self):
        return self.__dict__.get('datetime')


class Observation(float):

    def __init__(self, value, unit):
        self._raw = value
        self._unit = unit

    def __new__(cls, value, *args):
        return float.__new__(cls, value)

    @property
    def unit(self):
        return self._unit

    def __repr__(self):
        return "Observation({}, '{}')".format(self.__float__(), self.unit)

    def __str__(self):
        return "{} {}".format(self.__float__(), self.unit)
