# -*- coding: utf-8 -*-
"""The operating system file entry implementation."""

import os
import platform
import stat

import pysmdev

try:
  import xattr
except ImportError:
  xattr = None

from dfdatetime import posix_time as dfdatetime_posix_time

from dfvfs.lib import definitions
from dfvfs.path import os_path_spec
from dfvfs.vfs import attribute
from dfvfs.vfs import file_entry
from dfvfs.vfs import os_attribute
from dfvfs.vfs import os_directory


class OSFileEntry(file_entry.FileEntry):
  """File system file entry that uses os."""

  TYPE_INDICATOR = definitions.TYPE_INDICATOR_OS

  _OS_IS_WINDOWS = platform.system() == 'Windows'

  def __init__(self, resolver_context, file_system, path_spec, is_root=False):
    """Initializes a file entry.

    Args:
      resolver_context (Context): resolver context.
      file_system (FileSystem): file system.
      path_spec (PathSpec): path specification.
      is_root (Optional[bool]): True if the file entry is the root file entry
          of the corresponding file system.
    """
    location = getattr(path_spec, 'location', None)

    # Windows does not support running os.stat on device files so we use
    # libsmdev to do an initial check.
    is_windows_device = False
    if self._OS_IS_WINDOWS and location:
      try:
        # pylint: disable=no-member
        is_windows_device = pysmdev.check_device(location)
      except IOError:
        pass

    stat_info = None
    if not is_windows_device and location:
      # We are only catching OSError. However on the Windows platform
      # a WindowsError can be raised as well. We are not catching that since
      # that error does not exist on non-Windows platforms.
      try:
        stat_info = os.lstat(location)
      except (IOError, OSError):
        stat_info = None

    super(OSFileEntry, self).__init__(
        resolver_context, file_system, path_spec, is_root=is_root,
        is_virtual=False)
    self._is_windows_device = is_windows_device
    self._location = location
    self._name = None
    self._stat_info = stat_info

    if is_windows_device:
      self.entry_type = definitions.FILE_ENTRY_TYPE_DEVICE

    elif stat_info:
      # If location contains a trailing segment separator and points to
      # a symbolic link to a directory stat info will not indicate
      # the file entry as a symbolic link. The following check ensures
      # that the LINK type is correctly detected.
      is_link = os.path.islink(location)

      # The stat info member st_mode can have multiple types e.g.
      # LINK and DIRECTORY in case of a symbolic link to a directory
      # dfVFS currently only supports one type so we need to check
      # for LINK first.
      if stat.S_ISLNK(stat_info.st_mode) or is_link:
        self.entry_type = definitions.FILE_ENTRY_TYPE_LINK
      elif stat.S_ISREG(stat_info.st_mode):
        self.entry_type = definitions.FILE_ENTRY_TYPE_FILE
      elif stat.S_ISDIR(stat_info.st_mode):
        self.entry_type = definitions.FILE_ENTRY_TYPE_DIRECTORY
      elif (stat.S_ISCHR(stat_info.st_mode) or
            stat.S_ISBLK(stat_info.st_mode)):
        self.entry_type = definitions.FILE_ENTRY_TYPE_DEVICE
      elif stat.S_ISFIFO(stat_info.st_mode):
        self.entry_type = definitions.FILE_ENTRY_TYPE_PIPE
      elif stat.S_ISSOCK(stat_info.st_mode):
        self.entry_type = definitions.FILE_ENTRY_TYPE_SOCKET

  def _GetAttributes(self):
    """Retrieves the attributes.

    Returns:
      list[Attribute]: attributes.
    """
    if self._attributes is None:
      self._attributes = []

      if xattr:
        for name in xattr.listxattr(self._location):
          extended_attribute = os_attribute.OSExtendedAttribute(
              self._location, name)
          self._attributes.append(extended_attribute)

    return self._attributes

  def _GetDirectory(self):
    """Retrieves a directory.

    Returns:
      OSDirectory: a directory.
    """
    if self.entry_type != definitions.FILE_ENTRY_TYPE_DIRECTORY:
      return None

    return os_directory.OSDirectory(self._file_system, self.path_spec)

  def _GetLink(self):
    """Retrieves the link.

    Returns:
      str: full path of the linked file entry.
    """
    if self._link is None:
      self._link = ''

      if self._location is None:
        return self._link

      self._link = os.readlink(self._location)
      self._link = os.path.abspath(self._link)

    return self._link

  def _GetStat(self):
    """Retrieves information about the file entry.

    Returns:
      VFSStat: a stat object or None if not available.
    """
    stat_object = super(OSFileEntry, self)._GetStat()

    if not self._is_windows_device and self._stat_info:
      # Ownership and permissions stat information.
      stat_object.mode = stat.S_IMODE(self._stat_info.st_mode)
      stat_object.uid = self._stat_info.st_uid
      stat_object.gid = self._stat_info.st_gid

      # Other stat information.
      stat_object.ino = self._stat_info.st_ino

    return stat_object

  def _GetStatAttribute(self):
    """Retrieves a stat attribute.

    Returns:
      StatAttribute: a stat attribute or None if not available.
    """
    stat_attribute = attribute.StatAttribute()

    if not self._is_windows_device and self._stat_info:
      stat_attribute.group_identifier = self._stat_info.st_gid
      stat_attribute.inode_number = self._stat_info.st_ino
      stat_attribute.mode = stat.S_IMODE(self._stat_info.st_mode)
      stat_attribute.number_of_links = self._stat_info.st_nlink
      stat_attribute.owner_identifier = self._stat_info.st_uid
      stat_attribute.size = self._stat_info.st_size

    stat_attribute.type = self.entry_type

    return stat_attribute

  def _GetSubFileEntries(self):
    """Retrieves sub file entries.

    Yields:
      OSFileEntry: a sub file entry.
    """
    if self._directory is None:
      self._directory = self._GetDirectory()

    if self._directory:
      for path_spec in self._directory.entries:
        yield OSFileEntry(self._resolver_context, self._file_system, path_spec)

  @property
  def access_time(self):
    """dfdatetime.DateTimeValues: access time or None if not available."""
    if self._stat_info is None:
      return None

    timestamp = getattr(self._stat_info, 'st_atime_ns', None)
    if timestamp is not None:
      return dfdatetime_posix_time.PosixTimeInNanoseconds(timestamp=timestamp)

    timestamp = int(self._stat_info.st_atime)
    return dfdatetime_posix_time.PosixTime(timestamp=timestamp)

  @property
  def change_time(self):
    """dfdatetime.DateTimeValues: change time or None if not available."""
    if self._stat_info is None:
      return None

    # Per Python os.stat() documentation the value of stat_results.st_ctime
    # contains the creation time on Windows.
    if self._OS_IS_WINDOWS:
      return None

    timestamp = getattr(self._stat_info, 'st_ctime_ns', None)
    if timestamp is not None:
      return dfdatetime_posix_time.PosixTimeInNanoseconds(timestamp=timestamp)

    timestamp = int(self._stat_info.st_ctime)
    return dfdatetime_posix_time.PosixTime(timestamp=timestamp)

  @property
  def creation_time(self):
    """dfdatetime.DateTimeValues: creation time or None if not available."""
    if self._stat_info is None:
      return None

    # Per Python os.stat() documentation the value of stat_results.st_ctime
    # contains the creation time on Windows.
    if self._OS_IS_WINDOWS:
      timestamp = getattr(self._stat_info, 'st_ctime_ns', None)
      if timestamp is not None:
        return dfdatetime_posix_time.PosixTimeInNanoseconds(timestamp=timestamp)

      timestamp = int(self._stat_info.st_ctime)

    else:
      timestamp = getattr(self._stat_info, 'st_birthtime', None)
      if timestamp is None:
        return None

    return dfdatetime_posix_time.PosixTime(timestamp=timestamp)

  @property
  def modification_time(self):
    """dfdatetime.DateTimeValues: modification time or None if not available."""
    if self._stat_info is None:
      return None

    timestamp = getattr(self._stat_info, 'st_mtime_ns', None)
    if timestamp is not None:
      return dfdatetime_posix_time.PosixTimeInNanoseconds(timestamp=timestamp)

    timestamp = int(self._stat_info.st_mtime)
    return dfdatetime_posix_time.PosixTime(timestamp=timestamp)

  @property
  def name(self):
    """str: name of the file entry, without the full path."""
    if self._name is None:
      if self._location is not None:
        self._name = self._file_system.BasenamePath(self._location)
    return self._name

  @property
  def size(self):
    """int: size of the file entry in bytes or None if not available."""
    if self._is_windows_device or not self._stat_info:
      return None

    return self._stat_info.st_size

  def GetLinkedFileEntry(self):
    """Retrieves the linked file entry, for example for a symbolic link.

    Returns:
      OSFileEntry: linked file entry or None if not available.
    """
    link = self._GetLink()
    if not link:
      return None

    path_spec = os_path_spec.OSPathSpec(location=link)
    return OSFileEntry(self._resolver_context, self._file_system, path_spec)

  def GetParentFileEntry(self):
    """Retrieves the parent file entry.

    Returns:
      OSFileEntry: parent file entry or None if not available.
    """
    if self._location is None:
      return None

    parent_location = self._file_system.DirnamePath(self._location)
    if parent_location is None:
      return None

    if parent_location == '':
      parent_location = self._file_system.PATH_SEPARATOR

    path_spec = os_path_spec.OSPathSpec(location=parent_location)
    return OSFileEntry(self._resolver_context, self._file_system, path_spec)
