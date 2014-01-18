#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright 2013 The dfVFS Project Authors.
# Please see the AUTHORS file for details on individual authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Tests for the volume system implementation using the SleuthKit (TSK)."""

import os
import unittest

from dfvfs.path import os_path_spec
from dfvfs.path import tsk_partition_path_spec
from dfvfs.volume import tsk_volume_system


class TSKVolumeSystemTest(unittest.TestCase):
  """The unit test for the SleuthKit (TSK) volume system object."""

  def setUp(self):
    """Sets up the needed objects used throughout the test."""
    test_file = os.path.join('test_data', 'tsk_volume_system.raw')

    path_spec = os_path_spec.OSPathSpec(location=test_file)
    self._tsk_path_spec = tsk_partition_path_spec.TSKPartitionPathSpec(
        location=u'/', parent=path_spec)

  # mmls test_data/tsk_volume_system.raw
  # DOS Partition Table
  # Offset Sector: 0
  # Units are in 512-byte sectors
  #
  #      Slot    Start        End          Length       Description
  # 00:  Meta    0000000000   0000000000   0000000001   Primary Table (#0)
  # 01:  -----   0000000000   0000000000   0000000001   Unallocated
  # 02:  00:00   0000000001   0000000350   0000000350   Linux (0x83)
  # 03:  Meta    0000000351   0000002879   0000002529   DOS Extended (0x05)
  # 04:  Meta    0000000351   0000000351   0000000001   Extended Table (#1)
  # 05:  -----   0000000351   0000000351   0000000001   Unallocated
  # 06:  01:00   0000000352   0000002879   0000002528   Linux (0x83)

  def testIterateVolumes(self):
    """Test the iterate volumes functionality."""
    volume_system = tsk_volume_system.TSKVolumeSystem()
    volume_system.Open(self._tsk_path_spec)

    self.assertEquals(volume_system.bytes_per_sector, 512)

    self.assertEquals(volume_system.number_of_sections, 7)
    self.assertEquals(volume_system.number_of_volumes, 2)

    volume = volume_system.GetVolumeByIndex(1)

    self.assertEquals(volume.number_of_extents, 1)
    self.assertEquals(volume.number_of_attributes, 2)
    self.assertEquals(volume.identifier, 'p2')


if __name__ == '__main__':
  unittest.main()