"""Tests for run_app.py — the cross-platform launcher."""

import os
import ssl
import sys
import tempfile
import unittest
import zipfile
from io import BytesIO
from unittest.mock import MagicMock, call, mock_open, patch

import run_app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(content: bytes, content_length: int | None = None):
    """Return a mock urllib response object."""
    resp = MagicMock()
    resp.read.side_effect = [content, b""]
    headers: dict[str, str] = {}
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    resp.headers.get = lambda key, default="": headers.get(key, default)
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# _venv_python
# ---------------------------------------------------------------------------

class TestVenvPython(unittest.TestCase):

    def test_windows_path(self):
        with patch("run_app.platform.system", return_value="Windows"):
            path = run_app._venv_python()
        self.assertTrue(path.endswith(os.path.join("venv", "Scripts", "python.exe")))

    def test_unix_path(self):
        for system in ("Darwin", "Linux"):
            with patch("run_app.platform.system", return_value=system):
                path = run_app._venv_python()
            self.assertTrue(
                path.endswith(os.path.join("venv", "bin", "python")),
                f"Wrong path for {system}: {path}",
            )

    def test_path_is_under_script_dir(self):
        with patch("run_app.platform.system", return_value="Linux"):
            path = run_app._venv_python()
        self.assertTrue(path.startswith(run_app.SCRIPT_DIR))


# ---------------------------------------------------------------------------
# _re_exec_in_venv
# ---------------------------------------------------------------------------

class TestReExecInVenv(unittest.TestCase):

    def test_already_in_venv_returns_none(self):
        """When sys.executable resolves to the venv python, do nothing."""
        fake_exe = "/proj/venv/bin/python"
        with (
            patch("run_app._venv_python", return_value=fake_exe),
            patch("os.path.realpath", return_value=fake_exe),
        ):
            result = run_app._re_exec_in_venv()
        self.assertIsNone(result)

    def test_missing_venv_exits_1(self):
        """If the venv python binary doesn't exist, print an error and exit(1)."""
        fake_venv_py = "/proj/venv/bin/python"
        with (
            patch("run_app._venv_python", return_value=fake_venv_py),
            patch("os.path.realpath", side_effect=lambda p: p),
            patch("os.path.isfile", return_value=False),
            patch("run_app.sys.exit", side_effect=SystemExit) as mock_exit,
            patch("builtins.print"),
        ):
            with self.assertRaises(SystemExit):
                run_app._re_exec_in_venv()
            mock_exit.assert_called_once_with(1)

    def test_missing_venv_unix_message(self):
        """On non-Windows, the error message mentions python3 and source."""
        fake_venv_py = "/proj/venv/bin/python"
        printed: list[str] = []
        with (
            patch("run_app._venv_python", return_value=fake_venv_py),
            patch("os.path.realpath", side_effect=lambda p: p),
            patch("os.path.isfile", return_value=False),
            patch("run_app.platform.system", return_value="Linux"),
            patch("run_app.sys.exit", side_effect=SystemExit),
            patch("builtins.print", side_effect=lambda *a, **kw: printed.append(" ".join(str(x) for x in a))),
        ):
            with self.assertRaises(SystemExit):
                run_app._re_exec_in_venv()
        full_output = " ".join(printed)
        self.assertIn("python3", full_output)
        self.assertIn("source", full_output)

    def test_missing_venv_windows_message(self):
        """On Windows, the error message mentions venv\\Scripts\\pip."""
        fake_venv_py = "C:\\proj\\venv\\Scripts\\python.exe"
        printed: list[str] = []
        with (
            patch("run_app._venv_python", return_value=fake_venv_py),
            patch("os.path.realpath", side_effect=lambda p: p),
            patch("os.path.isfile", return_value=False),
            patch("run_app.platform.system", return_value="Windows"),
            patch("run_app.sys.exit", side_effect=SystemExit),
            patch("builtins.print", side_effect=lambda *a, **kw: printed.append(" ".join(str(x) for x in a))),
        ):
            with self.assertRaises(SystemExit):
                run_app._re_exec_in_venv()
        full_output = " ".join(printed)
        self.assertIn("Scripts", full_output)

    def test_re_execs_and_exits_with_returncode(self):
        """When venv exists but we're not in it, re-exec and propagate exit code."""
        fake_venv_py = "/proj/venv/bin/python"
        with (
            patch("run_app._venv_python", return_value=fake_venv_py),
            patch("os.path.realpath", side_effect=lambda p: p + "_resolved"),
            patch("os.path.isfile", return_value=True),
            patch("run_app.subprocess.run", return_value=MagicMock(returncode=42)) as mock_run,
            patch("run_app.sys.exit") as mock_exit,
        ):
            run_app._re_exec_in_venv()
            mock_run.assert_called_once()
            mock_exit.assert_called_once_with(42)


# ---------------------------------------------------------------------------
# _ensure_deps
# ---------------------------------------------------------------------------

class TestEnsureDeps(unittest.TestCase):

    def test_does_nothing_when_deps_present(self):
        """When all three packages import fine, no pip call should occur."""
        with (
            patch("run_app.subprocess.check_call") as mock_cc,
            patch.dict("sys.modules", {"vosk": MagicMock(), "pyaudio": MagicMock(), "jellyfish": MagicMock()}),
        ):
            run_app._ensure_deps()
            mock_cc.assert_not_called()

    def test_installs_on_import_error(self):
        """When a package is missing (ImportError), pip install is triggered."""
        with (
            patch("builtins.__import__", side_effect=ImportError("no module")),
            patch("run_app.subprocess.check_call") as mock_cc,
            patch("builtins.print"),
        ):
            run_app._ensure_deps()
            mock_cc.assert_called_once()
            cmd = mock_cc.call_args[0][0]
            self.assertIn("-m", cmd)
            self.assertIn("pip", cmd)
            self.assertIn("install", cmd)
            self.assertIn("-r", cmd)

    def test_install_uses_requirements_txt(self):
        """Pip install command references requirements.txt in SCRIPT_DIR."""
        with (
            patch("builtins.__import__", side_effect=ImportError),
            patch("run_app.subprocess.check_call") as mock_cc,
            patch("builtins.print"),
        ):
            run_app._ensure_deps()
            cmd = mock_cc.call_args[0][0]
            req_path = cmd[-1]
            self.assertTrue(req_path.endswith("requirements.txt"))
            self.assertTrue(req_path.startswith(run_app.SCRIPT_DIR))


# ---------------------------------------------------------------------------
# _download_with_progress
# ---------------------------------------------------------------------------

class TestDownloadWithProgress(unittest.TestCase):

    def test_writes_content_to_dest(self):
        """Downloaded bytes must be written to the destination file."""
        content = b"hello world"
        mock_resp = _make_mock_response(content, content_length=len(content))
        m = mock_open()
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("builtins.open", m),
            patch("builtins.print"),
        ):
            run_app._download_with_progress("https://example.com/x.zip", "/tmp/x.zip")
        handle = m()
        handle.write.assert_called_once_with(content)

    def test_prints_progress_when_content_length_known(self):
        """When Content-Length is available, a percentage line is printed."""
        content = b"x" * 1024
        mock_resp = _make_mock_response(content, content_length=len(content))
        printed: list[str] = []
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("builtins.open", mock_open()),
            patch("builtins.print", side_effect=lambda *a, **kw: printed.append(str(a))),
        ):
            run_app._download_with_progress("https://example.com/x.zip", "/tmp/x.zip")
        # A progress line with '%' should have been printed
        self.assertTrue(any("%" in line for line in printed))

    def test_no_crash_when_content_length_missing(self):
        """If Content-Length header is absent, download completes without error."""
        content = b"data"
        mock_resp = _make_mock_response(content)  # no Content-Length
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("builtins.open", mock_open()),
            patch("builtins.print"),
        ):
            run_app._download_with_progress("https://example.com/x.zip", "/tmp/x.zip")

    def test_prints_url(self):
        """The URL is printed at the start of the download."""
        url = "https://example.com/model.zip"
        mock_resp = _make_mock_response(b"")
        printed: list[str] = []
        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch("builtins.open", mock_open()),
            patch("builtins.print", side_effect=lambda *a, **kw: printed.append(" ".join(str(x) for x in a))),
        ):
            run_app._download_with_progress(url, "/tmp/x.zip")
        self.assertTrue(any(url in line for line in printed))

    def test_uses_verified_ssl_context(self):
        """urlopen is called with an explicit SSL context (not the implicit default)."""
        mock_resp = _make_mock_response(b"data")
        captured_kwargs: list[dict] = []

        def fake_urlopen(url, context=None):
            captured_kwargs.append({"url": url, "context": context})
            return mock_resp

        with (
            patch("urllib.request.urlopen", side_effect=fake_urlopen),
            patch("builtins.open", mock_open()),
            patch("builtins.print"),
        ):
            run_app._download_with_progress("https://example.com/x.zip", "/tmp/x.zip")

        self.assertEqual(len(captured_kwargs), 1)
        ctx = captured_kwargs[0]["context"]
        self.assertIsNotNone(ctx, "SSL context must be passed explicitly")
        self.assertIsInstance(ctx, ssl.SSLContext)


# ---------------------------------------------------------------------------
# _ensure_model
# ---------------------------------------------------------------------------

class TestEnsureModel(unittest.TestCase):

    def _isdir(self, *existing_dirs):
        """Return a side-effect function: True when path is in *existing_dirs*."""
        def side_effect(path):
            return any(path.endswith(d) for d in existing_dirs)
        return side_effect

    def test_large_model_present_returns_immediately(self):
        printed: list[str] = []
        with (
            patch("os.path.isdir", side_effect=self._isdir(run_app.MODEL_LARGE_DIR)),
            patch("builtins.print", side_effect=lambda *a, **kw: printed.append(" ".join(str(x) for x in a))),
        ):
            run_app._ensure_model()
        self.assertTrue(any(run_app.MODEL_LARGE_DIR in line for line in printed))

    def test_small_model_present_returns_immediately(self):
        printed: list[str] = []
        with (
            patch("os.path.isdir", side_effect=self._isdir(run_app.MODEL_SMALL_DIR)),
            patch("builtins.print", side_effect=lambda *a, **kw: printed.append(" ".join(str(x) for x in a))),
        ):
            run_app._ensure_model()
        self.assertTrue(any(run_app.MODEL_SMALL_DIR in line for line in printed))

    def test_no_model_triggers_download(self):
        """When neither model directory exists, _download_with_progress is called."""
        with (
            patch("os.path.isdir", return_value=False),
            patch("run_app._download_with_progress") as mock_dl,
            patch("builtins.print"),
            patch("zipfile.ZipFile"),
            patch("os.remove"),
        ):
            run_app._ensure_model()
            mock_dl.assert_called_once()
            url_arg = mock_dl.call_args[0][0]
            self.assertEqual(url_arg, run_app.MODEL_LARGE_URL)

    def test_no_model_extracts_zip(self):
        """After download, _safe_extract_all is called and zip is removed."""
        with (
            patch("os.path.isdir", return_value=False),
            patch("run_app._download_with_progress"),
            patch("builtins.print"),
            patch("zipfile.ZipFile") as mock_zip_cls,
            patch("run_app._safe_extract_all") as mock_extract,
            patch("os.remove") as mock_rm,
        ):
            mock_zip_cls.return_value.__enter__ = lambda s: s
            mock_zip_cls.return_value.__exit__ = MagicMock(return_value=False)
            run_app._ensure_model()
            mock_zip_cls.assert_called_once()
            mock_extract.assert_called_once()
            # Second arg to _safe_extract_all is the destination dir
            self.assertEqual(mock_extract.call_args[0][1], run_app.SCRIPT_DIR)
            mock_rm.assert_called_once()

    def test_keyboard_interrupt_cleans_up_zip_and_exits(self):
        """On Ctrl+C, any partial zip is removed and sys.exit(1) is called."""
        zip_path = os.path.join(run_app.SCRIPT_DIR, "vosk-model.zip")
        with (
            patch("os.path.isdir", return_value=False),
            patch("run_app._download_with_progress", side_effect=KeyboardInterrupt),
            patch("builtins.print"),
            patch("os.path.exists", return_value=True),
            patch("os.remove") as mock_rm,
            patch("run_app.sys.exit", side_effect=SystemExit) as mock_exit,
        ):
            with self.assertRaises(SystemExit):
                run_app._ensure_model()
            mock_rm.assert_called_once_with(zip_path)
            mock_exit.assert_called_once_with(1)

    def test_keyboard_interrupt_no_zip_no_remove(self):
        """On Ctrl+C when zip doesn't exist yet, os.remove is not called."""
        with (
            patch("os.path.isdir", return_value=False),
            patch("run_app._download_with_progress", side_effect=KeyboardInterrupt),
            patch("builtins.print"),
            patch("os.path.exists", return_value=False),
            patch("os.remove") as mock_rm,
            patch("run_app.sys.exit", side_effect=SystemExit),
        ):
            with self.assertRaises(SystemExit):
                run_app._ensure_model()
            mock_rm.assert_not_called()

    def test_large_model_preferred_over_small(self):
        """If the large model exists, the small-model branch is never reached."""
        printed: list[str] = []
        with (
            patch("os.path.isdir", return_value=True),  # both "exist"
            patch("builtins.print", side_effect=lambda *a, **kw: printed.append(" ".join(str(x) for x in a))),
        ):
            run_app._ensure_model()
        # Only the large-model message should appear
        self.assertTrue(any(run_app.MODEL_LARGE_DIR in line for line in printed))
        self.assertFalse(any(run_app.MODEL_SMALL_DIR in line for line in printed))


# ---------------------------------------------------------------------------
# _safe_extract_all  (Zip Slip defence)
# ---------------------------------------------------------------------------

class TestSafeExtractAll(unittest.TestCase):
    """Verify that _safe_extract_all blocks path-traversal zip entries."""

    def _make_zip(self, members: list[tuple[str, bytes]]) -> str:
        """Write a temporary zip containing *members* and return its path."""
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp.close()
        with zipfile.ZipFile(tmp.name, "w") as zf:
            for name, data in members:
                zf.writestr(name, data)
        return tmp.name

    def test_safe_members_extract_successfully(self):
        """Normal members inside the dest dir are extracted without error."""
        with tempfile.TemporaryDirectory() as dest:
            zip_path = self._make_zip([("subdir/file.txt", b"hello")])
            with zipfile.ZipFile(zip_path, "r") as zf:
                run_app._safe_extract_all(zf, dest)
            self.assertTrue(os.path.exists(os.path.join(dest, "subdir", "file.txt")))

    def test_path_traversal_dot_dot_blocked(self):
        """A member with '../' in its path is blocked."""
        with tempfile.TemporaryDirectory() as dest:
            zip_path = self._make_zip([("../evil.txt", b"bad")])
            with zipfile.ZipFile(zip_path, "r") as zf:
                with self.assertRaises(ValueError, msg="Zip Slip should be blocked"):
                    run_app._safe_extract_all(zf, dest)

    def test_absolute_path_member_blocked(self):
        """A member whose name is an absolute path is blocked."""
        with tempfile.TemporaryDirectory() as dest:
            # zipfile allows writing absolute names directly
            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            tmp.close()
            import zipfile as zfmod
            with zfmod.ZipFile(tmp.name, "w") as zf:
                info = zfmod.ZipInfo("/etc/evil.txt")
                zf.writestr(info, b"bad")
            with zfmod.ZipFile(tmp.name, "r") as zf:
                with self.assertRaises(ValueError, msg="Absolute path in zip should be blocked"):
                    run_app._safe_extract_all(zf, dest)

    def test_deeply_nested_safe_path_allowed(self):
        """Deeply nested but safe paths are allowed."""
        with tempfile.TemporaryDirectory() as dest:
            zip_path = self._make_zip([("a/b/c/d/e.txt", b"data")])
            with zipfile.ZipFile(zip_path, "r") as zf:
                run_app._safe_extract_all(zf, dest)
            self.assertTrue(os.path.exists(os.path.join(dest, "a", "b", "c", "d", "e.txt")))


# ---------------------------------------------------------------------------
# Constants sanity checks
# ---------------------------------------------------------------------------

class TestConstants(unittest.TestCase):

    def test_script_dir_is_absolute(self):
        self.assertTrue(os.path.isabs(run_app.SCRIPT_DIR))

    def test_model_urls_use_https(self):
        self.assertTrue(run_app.MODEL_LARGE_URL.startswith("https://"))
        self.assertTrue(run_app.MODEL_SMALL_URL.startswith("https://"))

    def test_model_dir_names(self):
        self.assertEqual(run_app.MODEL_LARGE_DIR, "vosk-model-en-us-0.22")
        self.assertEqual(run_app.MODEL_SMALL_DIR, "vosk-model-small-en-us-0.15")


if __name__ == "__main__":
    unittest.main()
