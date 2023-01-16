import io
import os
import stat
import tempfile

import pytest

from dirdiff.filelib import StatInfo
from dirdiff.osshim import major, makedev, minor
from dirdiff.output_file import OutputBackendFile

# pylint: disable=redefined-outer-name


def _check_mode(actual: int, expected: int) -> None:
    """
    Check that the file type and permissions match. On windows we ignore the
    permissions since they aren't supported. Note that some file systems, even on
    unix systems, don't support permissions (like NTFS). For the purposes of this test
    however we assume that an appropriate unix-capable file system is used for temp
    directories on a unix system.
    """
    assert stat.S_IFMT(actual) == stat.S_IFMT(expected)
    if os.name == "nt":
        return
    actual_perms = stat.S_IMODE(actual)
    expected_perms = stat.S_IMODE(expected)
    assert actual_perms == expected_perms


def stat_with_defaults(
    mode: int = 0o755,
    uid: int = 1234,
    gid: int = 4567,
    size: int = 0,
    mtime: int = 0,
    rdev: int = 0,
) -> StatInfo:
    return StatInfo(mode, uid, gid, size, mtime, rdev)


@pytest.fixture
def file_backend():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield OutputBackendFile(tmp_dir)


@pytest.fixture
def file_backend_preserve():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield OutputBackendFile(tmp_dir, preserve_owners=True)


def test_file_write_dir(file_backend):
    mode = 0o755 | stat.S_IFDIR
    file_name = "my-dir"
    st = stat_with_defaults(mode=mode)
    file_backend.write_dir(file_name, st)

    file_path = os.path.join(file_backend.base_path, file_name)
    st = os.lstat(file_path)
    _check_mode(st.st_mode, mode)
    assert not os.listdir(file_path)


def test_file_write_reg(file_backend):
    mode = 0o644 | stat.S_IFREG
    data = b"Hello dirdiff!"
    file_name = "my-file"

    st = stat_with_defaults(mode=mode, size=len(data))
    file_backend.write_file(file_name, st, io.BytesIO(data))

    file_path = os.path.join(file_backend.base_path, file_name)
    st = os.lstat(file_path)
    _check_mode(st.st_mode, mode)
    with open(file_path, "rb") as fdata:
        assert fdata.read() == data


def test_file_write_link(file_backend):
    mode = 0o644 | stat.S_IFREG
    data = b"Hello dirdiff!"
    file_name = "my-file"

    st = stat_with_defaults(mode=mode, size=len(data))
    file_backend.write_file(file_name, st, io.BytesIO(data))

    sym_mode = 0o777 | stat.S_IFLNK
    sym_file_name = "my-link"
    sym_st = stat_with_defaults(mode=sym_mode)
    file_backend.write_symlink(sym_file_name, sym_st, file_name)

    sym_file_path = os.path.join(file_backend.base_path, sym_file_name)
    st = os.lstat(sym_file_path)
    # Permission bits on symlinks are irrelevant, some OS/FS do different things
    assert stat.S_ISLNK(st.st_mode)
    assert os.readlink(sym_file_path) == file_name

    st = os.stat(sym_file_path)
    _check_mode(st.st_mode, mode)
    with open(sym_file_path, "rb") as fdata:
        assert fdata.read() == data


@pytest.mark.unix
@pytest.mark.cap
@pytest.mark.cap_mknod
@pytest.mark.parametrize(
    "ftype",
    [
        pytest.param(stat.S_IFCHR, id="chr"),
        pytest.param(stat.S_IFBLK, id="blk"),
    ],
)
def test_file_write_device(ftype, file_backend):
    mode = 0o600 | ftype
    file_name = "my-dev"
    dev_major = 12
    dev_minor = 7

    st = stat_with_defaults(mode=mode, rdev=makedev(dev_major, dev_minor))
    file_backend.write_other(file_name, st)

    file_path = os.path.join(file_backend.base_path, file_name)
    st = os.lstat(file_path)
    _check_mode(st.st_mode, mode)
    assert major(st.st_rdev) == dev_major
    assert minor(st.st_rdev) == dev_minor


@pytest.mark.unix
@pytest.mark.cap
@pytest.mark.cap_chown
def test_file_write_chown(file_backend_preserve):
    mode = 0o644 | stat.S_IFREG
    data = b"Hello dirdiff!"
    file_name = "my-file"
    uid = 123
    gid = 543

    st = stat_with_defaults(mode=mode, size=len(data), uid=uid, gid=gid)
    file_backend_preserve.write_file(file_name, st, io.BytesIO(data))

    file_path = os.path.join(file_backend_preserve.base_path, file_name)
    st = os.lstat(file_path)
    _check_mode(st.st_mode, mode)
    assert st.st_uid == uid
    assert st.st_gid == gid
    with open(file_path, "rb") as fdata:
        assert fdata.read() == data


@pytest.mark.unix
@pytest.mark.parametrize(
    "ftype",
    [
        pytest.param(stat.S_IFSOCK, id="sock"),
        pytest.param(stat.S_IFIFO, id="fifo"),
    ],
)
def test_file_write_sock(ftype, file_backend):
    mode = 0o600 | ftype
    file_name = "my-sock"

    st = stat_with_defaults(mode=mode)
    file_backend.write_other(file_name, st)

    file_path = os.path.join(file_backend.base_path, file_name)
    st = os.lstat(file_path)
    _check_mode(st.st_mode, mode)