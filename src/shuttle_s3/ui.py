from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QObject,
    QRunnable,
    QStandardPaths,
    QStringListModel,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .auth import AuthenticationCancelled, DeviceAuthorization, SsoAuthenticator
from .jobs import JobStore, SavedJob
from .matching import fuzzy_matches
from .profiles import ProfileError, SsoProfile, load_sso_profiles
from .s3 import (
    RemoteEntry,
    S3Service,
    TransferCancelled,
    TransferPlan,
    format_bytes,
)
from .updater import AvailableUpdate, UpdateClient, install_and_restart


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    status = Signal(str)
    device = Signal(object)
    progress = Signal(int, int, str)
    log = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, function: Callable[[WorkerSignals], Any]) -> None:
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self.function(self.signals)
        except (AuthenticationCancelled, TransferCancelled):
            self.signals.status.emit("Cancelled")
        except Exception as error:
            self.signals.error.emit(str(error))
        else:
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Shuttle — an S3 client")
        self.resize(1050, 760)
        self.thread_pool = QThreadPool.globalInstance()
        self.active_workers: set[Worker] = set()
        self.cancel_event = threading.Event()
        self.profiles: dict[str, SsoProfile] = {}
        self.authenticator = SsoAuthenticator()
        self.service: S3Service | None = None
        self.authenticated_profile_name: str | None = None
        self.current_plan: TransferPlan | None = None
        self.remote_entries: list[RemoteEntry] = []
        self.browsed_bucket = ""
        self.browsed_prefix = ""
        self.bucket_names: list[str] = []
        self.update_client = UpdateClient()
        self.background_workers: set[Worker] = set()

        data_root = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
        self.job_store = JobStore(Path(data_root) / "jobs.json")
        self.jobs: list[SavedJob] = []

        self._build_ui()
        self._load_profiles()
        self._load_jobs()
        QTimer.singleShot(1500, self._check_for_updates)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)

        session_form = QFormLayout()
        profile_row = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.refresh_profiles_button = QPushButton("Refresh")
        self.sign_in_button = QPushButton("Sign in")
        profile_row.addWidget(self.profile_combo, 1)
        profile_row.addWidget(self.refresh_profiles_button)
        profile_row.addWidget(self.sign_in_button)
        session_form.addRow("IAM Identity Center profile:", profile_row)
        self.auth_status = QLabel("Not signed in")
        self.auth_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        session_form.addRow("Session:", self.auth_status)
        layout.addLayout(session_form)

        source_form = QFormLayout()
        bucket_row = QHBoxLayout()
        self.bucket_combo = QComboBox()
        self.bucket_combo.setEditable(True)
        self.bucket_completion_model = QStringListModel(self)
        self.bucket_completer = QCompleter(self.bucket_completion_model, self)
        self.bucket_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.bucket_completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.bucket_combo.setCompleter(self.bucket_completer)
        self.load_buckets_button = QPushButton("Load buckets")
        bucket_row.addWidget(self.bucket_combo, 1)
        bucket_row.addWidget(self.load_buckets_button)
        source_form.addRow("Bucket:", bucket_row)

        path_row = QHBoxLayout()
        self.source_edit = QLineEdit()
        self.source_edit.setPlaceholderText("reports/2025/ or reports/summary.csv")
        self.browse_s3_button = QPushButton("Browse")
        self.up_button = QPushButton("Up")
        path_row.addWidget(self.source_edit, 1)
        path_row.addWidget(self.up_button)
        path_row.addWidget(self.browse_s3_button)
        source_form.addRow("S3 path:", path_row)
        layout.addLayout(source_form)

        self.remote_table = QTableWidget(0, 3)
        self.remote_table.setHorizontalHeaderLabels(["Name", "Size", "Last modified"])
        self.remote_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.remote_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.remote_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.remote_table.setAlternatingRowColors(True)

        lower = QWidget()
        lower_layout = QVBoxLayout(lower)
        transfer_form = QFormLayout()
        destination_row = QHBoxLayout()
        self.destination_edit = QLineEdit()
        self.choose_destination_button = QPushButton("Choose…")
        destination_row.addWidget(self.destination_edit, 1)
        destination_row.addWidget(self.choose_destination_button)
        transfer_form.addRow("Local destination:", destination_row)

        options_row = QHBoxLayout()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Download / update", "download")
        self.mode_combo.addItem("Mirror (delete extra local files)", "mirror")
        self.overwrite_check = QCheckBox("Overwrite existing files")
        options_row.addWidget(self.mode_combo)
        options_row.addWidget(self.overwrite_check)
        options_row.addStretch()
        transfer_form.addRow("Options:", options_row)
        self.option_help = QLabel()
        self.option_help.setWordWrap(True)
        transfer_form.addRow("", self.option_help)
        lower_layout.addLayout(transfer_form)

        job_row = QHBoxLayout()
        self.job_combo = QComboBox()
        self.job_combo.addItem("Saved jobs…", None)
        self.save_job_button = QPushButton("Save current job")
        self.delete_job_button = QPushButton("Delete saved job")
        job_row.addWidget(self.job_combo, 1)
        job_row.addWidget(self.save_job_button)
        job_row.addWidget(self.delete_job_button)
        lower_layout.addLayout(job_row)

        action_row = QHBoxLayout()
        self.preview_button = QPushButton("Preview")
        self.run_now_button = QPushButton("Run now")
        self.run_now_button.setToolTip("Start without waiting for a separate preview step")
        self.run_button = QPushButton("Run")
        self.run_button.setEnabled(False)
        self.run_button.setToolTip("Build a successful preview before running the transfer")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        action_row.addStretch()
        action_row.addWidget(self.preview_button)
        action_row.addWidget(self.run_now_button)
        action_row.addWidget(self.run_button)
        action_row.addWidget(self.cancel_button)
        lower_layout.addLayout(action_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        lower_layout.addWidget(self.progress)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Transfer details and errors appear here.")
        lower_layout.addWidget(self.log, 1)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self.remote_table)
        splitter.addWidget(lower)
        splitter.setSizes([280, 350])
        layout.addWidget(splitter, 1)
        self.setCentralWidget(root)

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(QApplication.quit)
        self.menuBar().addMenu("File").addAction(exit_action)
        check_updates_action = QAction("Check for updates…", self)
        check_updates_action.triggered.connect(lambda: self._check_for_updates(manual=True))
        self.menuBar().addMenu("Help").addAction(check_updates_action)

        self.refresh_profiles_button.clicked.connect(self._load_profiles)
        self.profile_combo.currentTextChanged.connect(self._profile_changed)
        self.sign_in_button.clicked.connect(self._sign_in)
        self.load_buckets_button.clicked.connect(self._load_buckets)
        self.browse_s3_button.clicked.connect(self._browse_s3)
        self.up_button.clicked.connect(self._go_up)
        self.remote_table.cellClicked.connect(self._select_remote_entry)
        self.remote_table.cellDoubleClicked.connect(self._open_remote_entry)
        self.choose_destination_button.clicked.connect(self._choose_destination)
        self.preview_button.clicked.connect(self._preview)
        self.run_now_button.clicked.connect(self._run_now)
        self.run_button.clicked.connect(self._run)
        self.cancel_button.clicked.connect(self._cancel)
        self.save_job_button.clicked.connect(self._save_job)
        self.delete_job_button.clicked.connect(self._delete_job)
        self.job_combo.currentIndexChanged.connect(self._apply_job)
        self.source_edit.textChanged.connect(self._invalidate_plan)
        self.destination_edit.textChanged.connect(self._invalidate_plan)
        self.bucket_combo.currentTextChanged.connect(self._bucket_changed)
        self.bucket_combo.lineEdit().textEdited.connect(self._update_bucket_matches)
        self.mode_combo.currentIndexChanged.connect(self._invalidate_plan)
        self.mode_combo.currentIndexChanged.connect(self._update_option_help)
        self.overwrite_check.toggled.connect(self._invalidate_plan)
        self.overwrite_check.toggled.connect(self._update_option_help)
        self._update_option_help()

    def _load_profiles(self) -> None:
        selected = self.profile_combo.currentText()
        try:
            profiles = load_sso_profiles()
        except ProfileError as error:
            self._show_error(str(error))
            return
        self.profiles = {profile.name: profile for profile in profiles}
        self.profile_combo.clear()
        self.profile_combo.addItems(self.profiles)
        if selected in self.profiles:
            self.profile_combo.setCurrentText(selected)
        if not profiles:
            self.auth_status.setText("No IAM Identity Center profiles found in ~/.aws/config")
        else:
            self.auth_status.setText(f"Found {len(profiles)} profile(s); not signed in")

    def _load_jobs(self) -> None:
        self.jobs = self.job_store.load()
        self.job_combo.blockSignals(True)
        self.job_combo.clear()
        self.job_combo.addItem("Saved jobs…", None)
        for job in self.jobs:
            self.job_combo.addItem(job.name, job)
        self.job_combo.blockSignals(False)

    def _set_busy(self, busy: bool) -> None:
        self.cancel_button.setEnabled(busy)
        for widget in (
            self.profile_combo,
            self.refresh_profiles_button,
            self.sign_in_button,
            self.load_buckets_button,
            self.browse_s3_button,
            self.preview_button,
            self.run_now_button,
        ):
            widget.setEnabled(not busy)
        if busy:
            self.run_button.setEnabled(False)
        else:
            self.run_button.setEnabled(self.current_plan is not None)

    def _start_worker(
        self,
        function: Callable[[WorkerSignals], Any],
        result: Callable[[Any], None],
        finished: Callable[[], None] | None = None,
    ) -> None:
        self.cancel_event = threading.Event()
        self._set_busy(True)
        worker = Worker(function)
        worker.signals.result.connect(result)
        worker.signals.error.connect(self._show_error)
        worker.signals.status.connect(self.auth_status.setText)
        worker.signals.device.connect(self._show_device)
        worker.signals.progress.connect(self._update_progress)
        worker.signals.log.connect(self._append_activity_log)
        worker.signals.finished.connect(
            lambda active_worker=worker, callback=finished: self._worker_finished(
                active_worker, callback
            )
        )
        # Keep the Python wrapper and its signal object alive until the pool is done.
        self.active_workers.add(worker)
        self.thread_pool.start(worker)

    def _worker_finished(
        self,
        worker: Worker,
        callback: Callable[[], None] | None = None,
    ) -> None:
        self.active_workers.discard(worker)
        if callback is not None:
            callback()
        self._set_busy(bool(self.active_workers))

    def _start_background_worker(
        self,
        function: Callable[[WorkerSignals], Any],
        result: Callable[[Any], None],
        *,
        show_errors: bool,
    ) -> None:
        worker = Worker(function)
        self.background_workers.add(worker)
        worker.signals.result.connect(result)
        if show_errors:
            worker.signals.error.connect(self._show_error)
        worker.signals.finished.connect(
            lambda active_worker=worker: self.background_workers.discard(active_worker)
        )
        self.thread_pool.start(worker)

    def _check_for_updates(self, *, manual: bool = False) -> None:
        if self.background_workers:
            return

        def checked(update: Any) -> None:
            if update is None:
                if manual:
                    QMessageBox.information(
                        self,
                        "Shuttle updates",
                        f"Shuttle {__version__} is the latest version.",
                    )
                return
            self._offer_update(update)

        self._start_background_worker(
            lambda _signals: self.update_client.check(__version__),
            checked,
            show_errors=manual,
        )

    def _offer_update(self, update: AvailableUpdate) -> None:
        if self.active_workers:
            QTimer.singleShot(3000, lambda: self._offer_update(update))
            return
        answer = QMessageBox.question(
            self,
            "Shuttle update available",
            f"Shuttle {update.version} is available. You are using {__version__}.\n\n"
            "Download the update and restart Shuttle?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return
        self.log.appendPlainText(f"Downloading Shuttle {update.version} update…")
        self.progress.setValue(0)

        def download(signals: WorkerSignals) -> Any:
            return self.update_client.download(
                update,
                on_progress=signals.progress.emit,
            )

        def downloaded(path: Any) -> None:
            try:
                install_and_restart(path)
            except Exception as error:
                self._show_error(str(error))
                return
            QApplication.quit()

        self._start_worker(download, downloaded)

    def _sign_in(self) -> None:
        profile = self.profiles.get(self.profile_combo.currentText())
        if profile is None:
            self._show_error("Select an IAM Identity Center profile")
            return
        self.service = None
        self.authenticated_profile_name = None
        self.bucket_combo.clear()

        def authenticate(signals: WorkerSignals) -> Any:
            return self.authenticator.authenticate(
                profile,
                cancel=self.cancel_event,
                on_status=signals.status.emit,
                on_device=signals.device.emit,
            )

        def signed_in(authenticated: Any) -> None:
            self.service = S3Service(authenticated.boto_session.client("s3"))
            self.authenticated_profile_name = profile.name
            self.auth_status.setText(f"Signed in as {profile.name}")
            self.auth_status.setText(
                f"Signed in as {profile.name}. Select “Load buckets” to continue."
            )

        self._start_worker(authenticate, signed_in)

    def _profile_changed(self, profile_name: str) -> None:
        if self.service is None or profile_name == self.authenticated_profile_name:
            return
        self.cancel_event.set()
        self.service = None
        self.authenticated_profile_name = None
        self.bucket_combo.clear()
        self.auth_status.setText("Profile changed; sign in to continue")

    def _show_device(self, device: DeviceAuthorization) -> None:
        QMessageBox.information(
            self,
            "Complete sign-in",
            "Your browser has been opened for IAM Identity Center sign-in.\n\n"
            f"If requested, enter code: {device.user_code}\n\n"
            "Shuttle keeps this session in memory only.",
        )

    def _require_service(self) -> S3Service | None:
        if self.service is None:
            self._show_error("Sign in before accessing S3")
        return self.service

    def _load_buckets(self) -> None:
        service = self._require_service()
        if service is None:
            return
        current = self.bucket_combo.currentText()

        def loaded(buckets: Any) -> None:
            self.bucket_names = list(buckets)
            self.bucket_combo.clear()
            self.bucket_combo.addItems(self.bucket_names)
            self._update_bucket_matches("")
            if current and current in self.bucket_names:
                self.bucket_combo.setCurrentText(current)
            self.auth_status.setText(
                f"Signed in; {len(self.bucket_names)} accessible bucket(s)"
            )

        self._start_worker(
            lambda _signals: service.list_buckets(self.cancel_event),
            loaded,
        )

    def _update_bucket_matches(self, text: str) -> None:
        matches = fuzzy_matches(text, self.bucket_names)
        self.bucket_completion_model.setStringList(matches)
        if text and matches:
            self.bucket_completer.complete()

    def _bucket_changed(self, _bucket: str) -> None:
        self.source_edit.clear()
        self.remote_entries = []
        self.browsed_bucket = ""
        self.browsed_prefix = ""
        self.remote_table.clearContents()
        self.remote_table.setRowCount(0)
        self._invalidate_plan()

    def _browse_s3(self) -> None:
        service = self._require_service()
        if service is None:
            return
        bucket = self.bucket_combo.currentText().strip()
        prefix = self.source_edit.text().strip().lstrip("/")
        if prefix and not prefix.endswith("/"):
            prefix = f"{prefix}/"
            self.source_edit.setText(prefix)
        self._start_worker(
            lambda _signals: service.list_prefix(bucket, prefix, self.cancel_event),
            lambda entries: self._show_remote_entries(entries, bucket, prefix),
        )

    def _show_remote_entries(self, entries: Any, bucket: str, prefix: str) -> None:
        current_bucket = self.bucket_combo.currentText().strip()
        current_prefix = self.source_edit.text().strip().lstrip("/")
        if current_bucket != bucket or current_prefix != prefix:
            return
        self.remote_entries = list(entries)
        self.browsed_bucket = bucket
        self.browsed_prefix = prefix
        self.remote_table.setRowCount(len(self.remote_entries))
        for row, entry in enumerate(self.remote_entries):
            name = f"📁 {entry.name}" if entry.is_prefix else entry.name
            self.remote_table.setItem(row, 0, QTableWidgetItem(name))
            self.remote_table.setItem(
                row, 1, QTableWidgetItem("" if entry.is_prefix else format_bytes(entry.size))
            )
            modified = (
                entry.modified.astimezone().strftime("%Y-%m-%d %H:%M")
                if entry.modified
                else ""
            )
            self.remote_table.setItem(row, 2, QTableWidgetItem(modified))
        self.auth_status.setText(f"Loaded {len(entries)} item(s)")

    def _open_remote_entry(self, row: int, _column: int) -> None:
        if row >= len(self.remote_entries):
            return
        entry = self.remote_entries[row]
        self.source_edit.setText(entry.key)
        if entry.is_prefix:
            self._browse_s3()

    def _select_remote_entry(self, row: int, _column: int) -> None:
        if row < len(self.remote_entries):
            self.source_edit.setText(self.remote_entries[row].key)

    def _go_up(self) -> None:
        current = self.source_edit.text().strip().rstrip("/")
        parent = current.rpartition("/")[0]
        self.source_edit.setText(f"{parent}/" if parent else "")
        self._browse_s3()

    def _choose_destination(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            "Choose local destination",
            self.destination_edit.text() or str(Path.home()),
        )
        if path:
            self.destination_edit.setText(path)

    def _plan_inputs(self) -> dict[str, Any]:
        destination = self.destination_edit.text().strip()
        if not destination:
            raise ValueError("Choose a local destination")
        return {
            "bucket": self.bucket_combo.currentText().strip(),
            "source": self.source_edit.text().strip(),
            "destination": Path(destination),
            "mode": self.mode_combo.currentData(),
            "overwrite": self.overwrite_check.isChecked(),
        }

    def _known_browser_entries(self, inputs: dict[str, Any]) -> list[RemoteEntry] | None:
        normalized_source = inputs["source"].lstrip("/")
        normalized_prefix = (
            normalized_source
            if normalized_source.endswith("/")
            else f"{normalized_source}/"
        )
        if (
            inputs["bucket"] == self.browsed_bucket
            and normalized_prefix == self.browsed_prefix
            and not any(entry.is_prefix for entry in self.remote_entries)
        ):
            return self.remote_entries
        return None

    def _update_option_help(self, *_args: Any) -> None:
        mode = self.mode_combo.currentData()
        overwrite = self.overwrite_check.isChecked()
        if mode == "download" and not overwrite:
            text = "Downloads missing files. Existing files and extra local files are kept."
        elif mode == "download":
            text = (
                "Downloads every S3 file and replaces same-named local files. "
                "Extra local files are kept."
            )
        elif not overwrite:
            text = (
                "Adds missing files and deletes extra local files, but preserves the contents "
                "of same-named existing files."
            )
        else:
            text = (
                "Makes the destination match S3: downloads every file, replaces existing "
                "copies, and deletes extra local files."
            )
        self.option_help.setText(text)

    def _preview(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            inputs = self._plan_inputs()
        except ValueError as error:
            self._show_error(str(error))
            return
        self.current_plan = None
        self.run_button.setEnabled(False)
        self.log.setPlainText(
            "Building preview… Shuttle is listing the selected S3 path and checking "
            "the local destination. Large folders can take a while.\n"
        )
        self.auth_status.setText("Building transfer preview…")
        self.progress.setRange(0, 0)
        self.progress.setFormat("Building preview…")
        known_entries = self._known_browser_entries(inputs)

        def show(plan: Any) -> None:
            self.current_plan = plan
            self.run_button.setEnabled(True)
            self.run_button.setToolTip("Run the transfer shown in the preview")
            self.auth_status.setText("Preview ready")
            self.log.appendPlainText(
                f"\nPlan: {len(plan.downloads)} download(s), "
                f"{len(plan.skipped)} skipped, {len(plan.deletions)} deletion(s), "
                f"{format_bytes(plan.download_bytes)} to download.\n"
            )
            for item in plan.items:
                detail = item.key or str(item.path)
                self.log.appendPlainText(f"{item.action.upper():8} {detail}")

        def preview_finished() -> None:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setFormat("%p%")
            if self.current_plan is None:
                self.run_button.setToolTip(
                    "The preview did not complete; review the error and try again"
                )

        self._start_worker(
            lambda signals: service.plan(
                **inputs,
                cancel=self.cancel_event,
                known_entries=known_entries,
                on_status=lambda message: signals.status.emit(f"Preview: {message}"),
            ),
            show,
            preview_finished,
        )

    def _run_now(self) -> None:
        service = self._require_service()
        if service is None:
            return
        try:
            inputs = self._plan_inputs()
        except ValueError as error:
            self._show_error(str(error))
            return
        known_entries = self._known_browser_entries(inputs)
        self.current_plan = None
        self.log.clear()
        self.progress.setRange(0, 0)

        if inputs["mode"] == "download":
            self.log.setPlainText(
                "Starting without a full preview. Files will download as S3 listing "
                "pages arrive.\n"
            )
            self.auth_status.setText("Starting direct download…")

            def download(signals: WorkerSignals) -> Any:
                def report(message: str) -> None:
                    signals.status.emit(message)
                    signals.log.emit(message)

                return service.download_now(
                    bucket=inputs["bucket"],
                    source=inputs["source"],
                    destination=inputs["destination"],
                    overwrite=inputs["overwrite"],
                    cancel=self.cancel_event,
                    known_entries=known_entries,
                    on_status=report,
                    on_progress=signals.progress.emit,
                )

            self._start_worker(download, self._transfer_complete, self._transfer_finished)
            return

        self.log.setPlainText(
            "Mirror mode must inventory S3 and the local destination before it can safely "
            "delete files. Shuttle will run automatically when that safety scan finishes.\n"
        )
        self.auth_status.setText("Preparing mirror safety scan…")

        def prepare_mirror(signals: WorkerSignals) -> Any:
            return service.plan(
                **inputs,
                cancel=self.cancel_event,
                known_entries=known_entries,
                on_status=signals.status.emit,
            )

        def mirror_ready(plan: Any) -> None:
            self.current_plan = plan
            self.log.appendPlainText(
                f"\nSafety scan complete: {len(plan.downloads)} download(s), "
                f"{len(plan.skipped)} skipped, {len(plan.deletions)} deletion(s)."
            )
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self._run()

        self._start_worker(prepare_mirror, mirror_ready, self._transfer_finished)

    def _run(self) -> None:
        service = self._require_service()
        plan = self.current_plan
        if service is None or plan is None:
            return
        if plan.deletions:
            preview = "\n".join(str(item.path) for item in plan.deletions[:10])
            more = len(plan.deletions) - 10
            if more > 0:
                preview += f"\n…and {more} more"
            answer = QMessageBox.warning(
                self,
                "Confirm mirror deletions",
                f"Mirror mode will permanently delete {len(plan.deletions)} local file(s):\n\n"
                f"{preview}\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
        self.progress.setValue(0)

        def execute(signals: WorkerSignals) -> Any:
            return service.execute(
                plan,
                cancel=self.cancel_event,
                on_progress=signals.progress.emit,
                on_log=signals.log.emit,
            )

        self._start_worker(execute, self._transfer_complete, self._transfer_finished)

    def _transfer_complete(self, result: Any) -> None:
        self.log.appendPlainText(
            f"\nComplete: {result.downloaded} downloaded, {result.skipped} skipped, "
            f"{result.deleted} deleted, {len(result.failed)} failed."
        )
        for failure in result.failed:
            self.log.appendPlainText(f"FAILED   {failure}")
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        self.progress.setFormat("%p%")
        self.current_plan = None
        self.run_button.setEnabled(False)

    def _transfer_finished(self) -> None:
        if self.progress.maximum() == 0 and not self.active_workers:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setFormat("%p%")

    def _update_progress(self, completed: int, total: int, key: str) -> None:
        if total:
            self.progress.setRange(0, 100)
            self.progress.setValue(round(completed * 100 / total))
            self.progress.setFormat(f"%p% — {key}")
        else:
            self.progress.setRange(0, 0)
            self.progress.setFormat(f"Downloading — {key}")

    def _append_activity_log(self, message: str) -> None:
        timestamp = datetime.now().astimezone().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{timestamp}] {message}")

    def _cancel(self) -> None:
        self.cancel_event.set()
        self.auth_status.setText("Cancelling…")

    def _invalidate_plan(self, *_args: Any) -> None:
        self.current_plan = None
        self.run_button.setEnabled(False)

    def _save_job(self) -> None:
        from PySide6.QtWidgets import QInputDialog

        name, accepted = QInputDialog.getText(self, "Save job", "Job name:")
        if not accepted or not name.strip():
            return
        try:
            inputs = self._plan_inputs()
        except ValueError as error:
            self._show_error(str(error))
            return
        job = SavedJob(
            name=name.strip(),
            profile=self.profile_combo.currentText(),
            bucket=inputs["bucket"],
            source=inputs["source"],
            destination=str(inputs["destination"]),
            mode=inputs["mode"],
            overwrite=inputs["overwrite"],
        )
        self.jobs = [existing for existing in self.jobs if existing.name != job.name]
        self.jobs.append(job)
        self.job_store.save_all(self.jobs)
        self._load_jobs()
        self.job_combo.setCurrentText(job.name)

    def _delete_job(self) -> None:
        job = self.job_combo.currentData()
        if not isinstance(job, SavedJob):
            return
        self.jobs = [existing for existing in self.jobs if existing.name != job.name]
        self.job_store.save_all(self.jobs)
        self._load_jobs()

    def _apply_job(self, _index: int) -> None:
        job = self.job_combo.currentData()
        if not isinstance(job, SavedJob):
            return
        if job.profile in self.profiles:
            self.profile_combo.setCurrentText(job.profile)
        self.bucket_combo.setCurrentText(job.bucket)
        self.source_edit.setText(job.source)
        self.destination_edit.setText(job.destination)
        mode_index = self.mode_combo.findData(job.mode)
        if mode_index >= 0:
            self.mode_combo.setCurrentIndex(mode_index)
        self.overwrite_check.setChecked(job.overwrite)

    def _show_error(self, message: str) -> None:
        self.auth_status.setText("Error")
        self.log.appendPlainText(f"ERROR    {message}")
        QMessageBox.critical(self, "Shuttle", message)

    def closeEvent(self, event: Any) -> None:
        self.cancel_event.set()
        self.authenticator.clear()
        self.service = None
        self.authenticated_profile_name = None
        event.accept()

