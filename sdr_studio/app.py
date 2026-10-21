"""Desktop receiver with switchable light and dark UI. Run: python -m sdr_studio"""
from __future__ import annotations
import sys
import time
import csv
import shlex
import shutil
from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from .dsp import MODES, BANDWIDTHS, DEFAULT_BW
from .vfo import VFOPair
from .dual_vfo import VFOChannel, center_and_validate
from .signal_hints import signal_hint
from .digital_auto import RFMonitor
from .scan import frequency_range
from .decoder_catalog import DECODERS, decoder_template, decoder_description, stream_command
from .digital_stream import DigitalDecoderWorker, DecoderEvent, parse_decoder_line
from .hardware import discover
from .device_ids import encode_device_id, decode_device_id
from .memories import load_memories, save_memories
from .memory_groups import (groups, group_members, shortcut_memory, memory_group, merge_groups,
                            load_group_names, save_group_names, create_group, normalize_group,
    scan_candidates, scan_counts,
                            rename_group, delete_group, DEFAULT_GROUP, ALL_GROUPS)
from .signal_meter import PeakMeter, calibrated_s_reading
from .iq_files import metadata_file
from .worker import ReceiverWorker
from .themes import PALETTES, colors, build_stylesheet
from .tuning import (TUNING_STEPS, DEFAULT_STEP, tuning_step_hz, tuned_frequency_hz,
                     format_frequency_mhz, parse_frequency_mhz)

pg.setConfigOptions(antialias=False, imageAxisOrder='row-major', background='#09131f', foreground='#b7c9dc')




class Bus(QtCore.QObject):
    frame = QtCore.Signal(object, object, object, float)
    status = QtCore.Signal(str)
    ended = QtCore.Signal()
    tune_result = QtCore.Signal(object)
    rds_result = QtCore.Signal(object)
    digital_event = QtCore.Signal(object)
    digital_line = QtCore.Signal(str)
    digital_ended = QtCore.Signal()


class FrequencySpinBox(QtWidgets.QLineEdit):
    """Always-visible MHz entry, with integer-Hz model and explicit commit.

    This deliberately uses QLineEdit rather than QDoubleSpinBox: the former
    does not retain a stale/blank private editor while a live receiver is
    retuning. setValue() updates the *visible* text on every call. The public
    methods below maintain the API used by the existing receiver controls.
    """
    valueChanged = QtCore.Signal(float)
    stepRequested = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frequency_hz = 145_500_000
        self._minimum_hz = 10_000
        self._maximum_hz = 2_000_000_000
        self.setText(format_frequency_mhz(self._frequency_hz))
        self.editingFinished.connect(self.interpretText)

    def value(self):
        return self._frequency_hz / 1_000_000

    def setValue(self, frequency_mhz):
        hz = int(round(float(frequency_mhz) * 1_000_000))
        hz = min(self._maximum_hz, max(self._minimum_hz, hz))
        changed = hz != self._frequency_hz
        self._frequency_hz = hz
        # ALWAYS repaint the actual MHz. If a user cleared an unfinished edit,
        # a remote/scanner tuning update still cannot leave this box blank.
        self.setText(format_frequency_mhz(hz))
        if changed:
            self.valueChanged.emit(self.value())

    def minimum(self):
        return self._minimum_hz / 1_000_000

    def maximum(self):
        return self._maximum_hz / 1_000_000

    def setRange(self, minimum_mhz, maximum_mhz):
        self._minimum_hz = int(round(minimum_mhz * 1_000_000))
        self._maximum_hz = int(round(maximum_mhz * 1_000_000))
        if self._maximum_hz < self._minimum_hz:
            raise ValueError('Maximumfrequentie is lager dan minimumfrequentie')
        self.setValue(self.value())

    def setSingleStep(self, step_mhz):
        # Step arithmetic is managed by Window.tune_by_steps(), in integer Hz.
        pass

    def interpretText(self):
        hz = parse_frequency_mhz(self.text(), self._minimum_hz,
                                 self._maximum_hz)
        if hz is None:
            # Invalid / empty / incomplete input: restore the last valid value.
            self.setText(format_frequency_mhz(self._frequency_hz))
            return
        self.setValue(hz / 1_000_000)

    def stepBy(self, steps):
        self.stepRequested.emit(int(steps))

    def wheelEvent(self, event):
        degrees = event.angleDelta().y()
        if degrees:
            self.stepBy(round(degrees / 120) or (1 if degrees > 0 else -1))
        event.accept()

    def keyPressEvent(self, event):
        key = event.key()
        if (event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier
                and key in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right)):
            self.stepBy(1 if key == QtCore.Qt.Key.Key_Right else -1)
            event.accept()
            return
        if key in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Down):
            self.stepBy(1 if key == QtCore.Qt.Key.Key_Up else -1)
            event.accept()
            return
        if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            self.interpretText()
            event.accept()
            return
        if key == QtCore.Qt.Key.Key_Escape:
            self.setText(format_frequency_mhz(self._frequency_hz))
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        self.interpretText()
        super().focusOutEvent(event)


class MemoryEditDialog(QtWidgets.QDialog):
    """Add or edit one saved frequency, including its group membership."""

    def __init__(self, parent, group_names, memory=None):
        super().__init__(parent)
        self.setWindowTitle('Geheugenkanaal bewerken' if memory else 'Geheugenkanaal toevoegen')
        self.setMinimumWidth(400)
        memory = memory or {}
        form = QtWidgets.QFormLayout(self)
        self.group = QtWidgets.QComboBox()
        self.group.setEditable(True)
        self.group.addItems(group_names)
        self.group.setCurrentText(memory_group(memory) if memory else parent.mem_group.currentText()
                                  if parent.mem_group.currentText() != ALL_GROUPS else DEFAULT_GROUP)
        self.name = QtWidgets.QLineEdit(str(memory.get('name', '')))
        self.frequency = QtWidgets.QDoubleSpinBox()
        self.frequency.setRange(0.01, 2000.0)
        self.frequency.setDecimals(6)
        self.frequency.setSuffix(' MHz')
        self.frequency.setValue(float(memory.get('frequency', parent.get_freq())) / 1e6)
        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(MODES)
        self.mode.setCurrentText(str(memory.get('mode', parent.mode.currentText())))
        self.comment = QtWidgets.QPlainTextEdit(str(memory.get('comment', '')))
        self.comment.setMaximumHeight(75)
        self.favorite = QtWidgets.QCheckBox('Favoriet')
        self.favorite.setChecked(bool(memory.get('favorite', False)))
        self.shortcut = QtWidgets.QSpinBox()
        self.shortcut.setRange(0, 8)
        self.shortcut.setSpecialValueText('Geen')
        self.shortcut.setValue(int(memory.get('shortcut', 0) or 0))
        for label, control in [('Groep:', self.group), ('Naam:', self.name),
                               ('Frequentie:', self.frequency), ('Mode:', self.mode),
                               ('Opmerking:', self.comment), ('Sneltoets F1–F8:', self.shortcut)]:
            form.addRow(label, control)
        form.addRow('', self.favorite)
        self.scan_enabled = QtWidgets.QCheckBox('Meenemen in groepsscan')
        self.scan_enabled.setChecked(memory.get('scan_enabled', True) is not False)
        form.addRow('', self.scan_enabled)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok |
                                              QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def validate(self):
        try:
            normalize_group(self.group.currentText())
            if not self.name.text().strip():
                raise ValueError('Geef een naam voor dit kanaal.')
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, 'Geheugen', str(exc))
            return
        self.accept()

    def result_memory(self, old=None):
        result = dict(old or {})
        result.update(name=self.name.text().strip(),
                      frequency=round(self.frequency.value() * 1e6),
                      mode=self.mode.currentText(),
                      group=normalize_group(self.group.currentText()),
                      comment=self.comment.toPlainText().strip(),
                      favorite=self.favorite.isChecked(),
                      scan_enabled=self.scan_enabled.isChecked(),
                      shortcut=self.shortcut.value())
        return result


class ScanSelectionDialog(QtWidgets.QDialog):
    """Choose any subset of a group without deleting or renaming memories."""

    def __init__(self, parent, name, memories):
        super().__init__(parent)
        self.setWindowTitle(f'Scankanalen kiezen · {name}')
        self.resize(620, 570)
        self.items = sorted(memories,
                            key=lambda m: (memory_group(m).casefold(), int(m['frequency']), m['name'].casefold()))
        box = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel(f'Kies welke frequenties van {name} de scanner mag gebruiken. '
                                'De overige frequenties blijven opgeslagen en zijn gewoon af te stemmen.')
        info.setWordWrap(True)
        box.addWidget(info)
        self.table = QtWidgets.QTableWidget(len(self.items), 3)
        self.table.setHorizontalHeaderLabels(['Scannen / Naam', 'Frequentie (MHz)', 'Mode'])
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(1, 155)
        self.table.setColumnWidth(2, 100)
        for i, memory in enumerate(self.items):
            title = memory['name']
            if name == ALL_GROUPS:
                title = f'[{memory_group(memory)}] {title}'
            item = QtWidgets.QTableWidgetItem(title)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            item.setCheckState(QtCore.Qt.CheckState.Checked
                               if memory.get('scan_enabled', True) is not False
                               else QtCore.Qt.CheckState.Unchecked)
            self.table.setItem(i, 0, item)
            for column, text in ((1, f"{memory['frequency']/1e6:.6f}"),
                                 (2, memory['mode'])):
                cell = QtWidgets.QTableWidgetItem(str(text))
                cell.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
                self.table.setItem(i, column, cell)
        box.addWidget(self.table, 1)
        self.counter = QtWidgets.QLabel()
        box.addWidget(self.counter)
        tools = QtWidgets.QHBoxLayout()
        self.limit_count = QtWidgets.QSpinBox()
        self.limit_count.setRange(0, len(self.items))
        self.limit_count.setValue(min(10, len(self.items)))
        self.limit_count.setSuffix(f' van {len(self.items)}')
        tools.addWidget(QtWidgets.QLabel('Aantal:'))
        tools.addWidget(self.limit_count)
        for label, callback in (('Kies eerste N', self.select_first_n),
                                ('Alles', lambda: self.check_all(True)),
                                ('Geen', lambda: self.check_all(False))):
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(callback)
            tools.addWidget(b)
        box.addLayout(tools)
        self.table.itemChanged.connect(self.update_count)
        self.update_count()
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save |
                                              QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Save).setText('Selectie opslaan')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)

    def check_all(self, enabled):
        for row in range(len(self.items)):
            self.table.item(row, 0).setCheckState(QtCore.Qt.CheckState.Checked if enabled
                                                  else QtCore.Qt.CheckState.Unchecked)
        self.update_count()

    def select_first_n(self):
        amount = self.limit_count.value()
        for row in range(len(self.items)):
            self.table.item(row, 0).setCheckState(QtCore.Qt.CheckState.Checked if row < amount
                                                  else QtCore.Qt.CheckState.Unchecked)
        self.update_count()

    def update_count(self, *_):
        amount = sum(self.table.item(row, 0).checkState() == QtCore.Qt.CheckState.Checked
                     for row in range(len(self.items)))
        self.counter.setText(f'{amount} van {len(self.items)} frequenties geselecteerd voor de scanner')

    def selections(self):
        """Return (original dict, boolean) in the same order as the table."""
        return [(item, self.table.item(i, 0).checkState() == QtCore.Qt.CheckState.Checked)
                for i, item in enumerate(self.items)]


class Window(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('SDR Studio RX by M@rcello  |  v0.8.2 beta  |  GROEPSSCANNER + DIGITAL AUTO  |  RTL-SDR / Airspy R2')
        self.settings = QtCore.QSettings('SDR Studio RX', 'M@rcello')
        saved_theme = self.settings.value('theme', 'dark')
        self.theme = saved_theme if saved_theme in PALETTES else 'dark'
        self.resize(1500, 890)
        self.setMinimumSize(1040, 680)
        self.worker = None
        self.error_status = None
        self.decoder = None
        self.digital = None
        self.pending_decoder = False
        self.memories = load_memories()
        self.memory_group_names = load_group_names(self.memories)
        self.vfos = VFOPair()
        self._load_vfos()
        self._vfo_loading = False
        self._vfo_request_seq = 0
        self._syncing_region = False
        self._last_plot_center = None
        self._last_plot_rate = None
        self._event_count = 0
        self.peak_meter = PeakMeter()
        self._water_count = 0
        self._hint_at = 0.0
        self._auto_frame_at = 0.0
        self.rf_monitor = RFMonitor()
        self._auto_counters = {'rf': 0, 'protocol': 0}
        self._stereo_started = False
        self._pending_iq_replay = None
        self.last_rate = 2_400_000
        # The offset is tracked from a fixed anchor to avoid cumulative Hz
        # drift for non-integer 8.33 kHz steps.
        self._step_anchor_hz = 145_500_000
        self._step_count = 0
        self._internal_tune = False
        self.water = np.full((140, 8192), -110.0, dtype=np.float32)
        self.bus = Bus()
        self.bus.frame.connect(self.on_frame)
        self.bus.status.connect(self.on_status)
        self.bus.ended.connect(self.on_worker_ended)
        self.bus.tune_result.connect(self.on_tune_result)
        self.bus.rds_result.connect(self.on_rds_result)
        self.bus.digital_event.connect(self.on_decoder_event)
        self.bus.digital_line.connect(self.on_decoder_line)
        self.bus.digital_ended.connect(self.on_digital_ended)
        self.build_ui()
        self._restore_vfo_controls()
        self._update_vfo_labels()
        self._sync_passband()
        self.apply_theme(self.theme)
        self.refresh_memories()
        self.source_changed()
        self.step_changed(self.step_combo.currentText())

    def build_ui(self):
        root = QtWidgets.QWidget()
        root.setObjectName('appRoot')
        self.setCentralWidget(root)
        outer = QtWidgets.QVBoxLayout(root)
        outer.setContentsMargins(10, 9, 10, 7)
        outer.setSpacing(7)

        # Header: radio's primary operations are always visible.
        header = QtWidgets.QFrame()
        header.setObjectName('header')
        hl = QtWidgets.QHBoxLayout(header)
        hl.setContentsMargins(9, 7, 9, 7)
        hl.setSpacing(6)
        self.brand = QtWidgets.QLabel()
        self.brand.setMinimumWidth(188)
        hl.addWidget(self.brand)
        hl.addStretch(1)
        freq_title = QtWidgets.QLabel('MHz')
        freq_title.setToolTip('Voer een frequentie in MHz in; Enter bevestigt de afstemming')
        hl.addWidget(freq_title)
        self.freq = FrequencySpinBox()
        self.freq.setObjectName('frequencyInput')
        self.freq.setRange(0.01, 2_000)
        self.freq.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.freq.setValue(145.500)
        self.freq.setMinimumSize(219, 45)
        self.freq.setMaximumWidth(280)
        self.freq.setToolTip('Frequentie in MHz: typ direct en druk Enter. Muiswiel / ↑↓ / Ctrl+←→ stemmen met STEP.')
        self.freq.valueChanged.connect(self.frequency_changed)
        self.freq.stepRequested.connect(self.tune_by_steps)
        hl.addWidget(self.freq)
        hl.addWidget(QtWidgets.QLabel('STEP'))
        self.step_combo = QtWidgets.QComboBox()
        self.step_combo.setObjectName('stepSelector')
        self.step_combo.setMinimumWidth(115)
        self.step_combo.setToolTip('Kies de afstemstap voor de +/- knoppen, pijltjes en het muiswiel')
        self.step_combo.addItems([item.label for item in TUNING_STEPS])
        previous_step = self.settings.value('frequency_step', DEFAULT_STEP)
        chosen_step = previous_step if previous_step in [item.label for item in TUNING_STEPS] else DEFAULT_STEP
        self.step_combo.setCurrentText(chosen_step)
        self.step_combo.currentTextChanged.connect(self.step_changed)
        hl.addWidget(self.step_combo)
        self.tune_down_btn = QtWidgets.QPushButton('−')
        self.tune_down_btn.setObjectName('tuneButton')
        self.tune_down_btn.setFixedSize(34, 40)
        self.tune_down_btn.setToolTip('Frequentie één STEP lager')
        self.tune_down_btn.clicked.connect(lambda: self.tune_by_steps(-1))
        hl.addWidget(self.tune_down_btn)
        self.tune_up_btn = QtWidgets.QPushButton('+')
        self.tune_up_btn.setObjectName('tuneButton')
        self.tune_up_btn.setFixedSize(34, 40)
        self.tune_up_btn.setToolTip('Frequentie één STEP hoger')
        self.tune_up_btn.clicked.connect(lambda: self.tune_by_steps(1))
        hl.addWidget(self.tune_up_btn)
        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(MODES)
        self.mode.setCurrentText('NFM')
        self.mode.setMinimumWidth(75)
        self.mode.currentTextChanged.connect(self.mode_changed)
        hl.addWidget(self.mode)
        self.theme_button = QtWidgets.QPushButton()
        self.theme_button.setObjectName('themeButton')
        self.theme_button.setMinimumWidth(95)
        self.theme_button.setToolTip('Wissel licht/donker uiterlijk (Ctrl+T)')
        self.theme_button.setShortcut('Ctrl+T')
        self.theme_button.clicked.connect(self.toggle_theme)
        hl.addWidget(self.theme_button)
        self.start_btn = QtWidgets.QPushButton('▶  ONTVANGEN')
        self.start_btn.setObjectName('start')
        self.start_btn.clicked.connect(self.start_receiver)
        hl.addWidget(self.start_btn)
        self.stop_btn = QtWidgets.QPushButton('■  STOP')
        self.stop_btn.setObjectName('stop')
        self.stop_btn.clicked.connect(self.stop_receiver)
        self.stop_btn.setEnabled(False)
        hl.addWidget(self.stop_btn)
        outer.addWidget(header)

        # IC-SDR-inspired instrument rail with compact RF meter, frequency
        # readout, and squelch/volume. These are real receiver controls.
        dashboard = QtWidgets.QFrame()
        dashboard.setObjectName('dashboard')
        deck = QtWidgets.QHBoxLayout(dashboard)
        deck.setContentsMargins(7, 6, 7, 6)
        deck.setSpacing(7)

        def metric_card(heading):
            frame = QtWidgets.QFrame()
            frame.setObjectName('metricCard')
            col = QtWidgets.QVBoxLayout(frame)
            col.setContentsMargins(12, 7, 12, 7)
            col.setSpacing(4)
            heading_label = QtWidgets.QLabel(heading)
            heading_label.setObjectName('cardTitle')
            col.addWidget(heading_label)
            return frame, col

        signal_card, signal_col = metric_card('RF-METER  ·  SIGNAAL')
        signal_card.setMinimumWidth(220)
        self.meter = QtWidgets.QLabel('RF: -- dBFS')
        self.meter.setObjectName('meterValue')
        signal_col.addWidget(self.meter)
        self.peak_label = QtWidgets.QLabel('Piek: -- dBFS  ·  S-meter: niet gekalibreerd')
        self.peak_label.setObjectName('status')
        signal_col.addWidget(self.peak_label)
        self.signal_meter = QtWidgets.QProgressBar()
        self.signal_meter.setObjectName('signalBar')
        self.signal_meter.setRange(0, 100)
        self.signal_meter.setValue(0)
        self.signal_meter.setTextVisible(False)
        self.signal_meter.setMaximumHeight(12)
        signal_col.addWidget(self.signal_meter)
        self.receiver_status = QtWidgets.QLabel('Stand-by  ·  geen IQ-stream')
        self.receiver_status.setObjectName('status')
        signal_col.addWidget(self.receiver_status)
        deck.addWidget(signal_card, 2)

        tune_card, tune_col = metric_card('VFO A/B  ·  AFSTEMMEN')
        tune_card.setMinimumWidth(240)
        self.freq_label = QtWidgets.QLabel('145.500000')
        self.freq_label.setObjectName('frequency')
        self.freq_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        tune_col.addWidget(self.freq_label, 1)
        self.vfo_info = QtWidgets.QLabel('NFM  ·  SDR gereed')
        self.vfo_info.setObjectName('status')
        self.vfo_info.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        tune_col.addWidget(self.vfo_info)
        vfo_controls = QtWidgets.QHBoxLayout()
        self.vfo_a_btn = QtWidgets.QPushButton('A')
        self.vfo_b_btn = QtWidgets.QPushButton('B')
        for key, btn in (('A', self.vfo_a_btn), ('B', self.vfo_b_btn)):
            btn.setCheckable(True)
            btn.setObjectName('vfoSelect')
            btn.setToolTip(f'Selecteer VFO {key}; één audiokanaal tegelijk')
            btn.clicked.connect(lambda _=False, name=key: self.select_vfo(name))
            vfo_controls.addWidget(btn)
        self.vfo_a_btn.setChecked(True)
        self.vfo_swap_btn = QtWidgets.QPushButton('A ⇄ B')
        self.vfo_swap_btn.setToolTip('Wissel onmiddellijk naar de andere VFO')
        self.vfo_swap_btn.clicked.connect(self.swap_vfo)
        vfo_controls.addWidget(self.vfo_swap_btn)
        self.vfo_copy_btn = QtWidgets.QPushButton('A = B')
        self.vfo_copy_btn.setToolTip('Kopieer de actieve VFO naar de andere')
        self.vfo_copy_btn.clicked.connect(self.copy_vfo)
        vfo_controls.addWidget(self.vfo_copy_btn)
        tune_col.addLayout(vfo_controls)
        self.stereo_toggle = QtWidgets.QCheckBox('Dual RX  ·  A links / B rechts (stereo)')
        self.stereo_toggle.setToolTip('Twee NFM/AM/SSB-kanalen tegelijk, mits beide filters binnen hetzelfde IF-venster passen; 2,5 MSPS aanbevolen')
        tune_col.addWidget(self.stereo_toggle)
        self.standby_label = QtWidgets.QLabel('B: 145.525000 MHz')
        self.standby_label.setObjectName('status')
        self.standby_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        tune_col.addWidget(self.standby_label)
        bw_row = QtWidgets.QHBoxLayout()
        bw_row.addWidget(QtWidgets.QLabel('BW / filter:'))
        self.bandwidth_spin = QtWidgets.QSpinBox()
        self.bandwidth_spin.setRange(*[BANDWIDTHS['NFM'][0], BANDWIDTHS['NFM'][-1]])
        self.bandwidth_spin.setSingleStep(500)
        self.bandwidth_spin.setValue(DEFAULT_BW['NFM'])
        self.bandwidth_spin.setSuffix(' Hz')
        self.bandwidth_spin.setToolTip('Ontvangstfilter; aanpasbaar met de blauwe filtergrenzen in het spectrum')
        self.bandwidth_spin.valueChanged.connect(self.bandwidth_changed)
        bw_row.addWidget(self.bandwidth_spin, 1)
        tune_col.addLayout(bw_row)
        shift_row = QtWidgets.QHBoxLayout()
        shift_row.addWidget(QtWidgets.QLabel('PBT shift:'))
        self.pbt_shift = QtWidgets.QSpinBox()
        self.pbt_shift.setRange(-100000, 100000)
        self.pbt_shift.setSingleStep(100)
        self.pbt_shift.setSuffix(' Hz')
        self.pbt_shift.setToolTip('Verschuif het doorlaatfilter zonder de SDR-middenfrequentie te wijzigen')
        self.pbt_shift.valueChanged.connect(self.passband_shift_changed)
        shift_row.addWidget(self.pbt_shift, 1)
        tune_col.addLayout(shift_row)
        deck.addWidget(tune_card, 3)

        audio_card, audio_col = metric_card('AUDIO  ·  DIRECTE BEDIENING')
        audio_card.setMinimumWidth(270)
        controls = QtWidgets.QGridLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setHorizontalSpacing(9)
        controls.setVerticalSpacing(5)
        controls.addWidget(QtWidgets.QLabel('SQL'), 0, 0)
        self.sql = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.sql.setRange(-100, 0)
        self.sql.setValue(-60)
        self.sql.valueChanged.connect(self.sql_changed)
        controls.addWidget(self.sql, 0, 1)
        self.sql_label = QtWidgets.QLabel('-60 dBFS')
        self.sql_label.setMinimumWidth(60)
        controls.addWidget(self.sql_label, 0, 2)
        controls.addWidget(QtWidgets.QLabel('VOL'), 1, 0)
        self.vol = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.vol.setRange(0, 200)
        self.vol.setValue(70)
        self.vol.valueChanged.connect(self.volume_changed)
        controls.addWidget(self.vol, 1, 1)
        self.vol_label = QtWidgets.QLabel('70%')
        controls.addWidget(self.vol_label, 1, 2)
        audio_col.addLayout(controls)
        self.capture_btn = QtWidgets.QPushButton('● WAV opname')
        self.capture_btn.setCheckable(True)
        self.capture_btn.setEnabled(False)
        self.capture_btn.toggled.connect(self.toggle_recording)
        audio_col.addWidget(self.capture_btn)
        deck.addWidget(audio_card, 3)
        outer.addWidget(dashboard)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(5)
        outer.addWidget(splitter, 1)
        receiver_pane = QtWidgets.QWidget()
        left = QtWidgets.QVBoxLayout(receiver_pane)
        left.setContentsMargins(0, 0, 2, 0)
        left.setSpacing(5)
        splitter.addWidget(receiver_pane)

        self.sidebar = QtWidgets.QTabWidget()
        self.sidebar.setDocumentMode(True)
        self.sidebar.setMinimumWidth(305)
        self.sidebar.setMaximumWidth(420)
        self.sidebar.setObjectName('sidebar')
        splitter.addWidget(self.sidebar)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setSizes([1115, 355])

        hardware_tab = QtWidgets.QWidget()
        s = QtWidgets.QVBoxLayout(hardware_tab)
        s.setContentsMargins(6, 9, 6, 6)
        hardware_scroll = QtWidgets.QScrollArea()
        hardware_scroll.setWidgetResizable(True)
        hardware_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        hardware_scroll.setWidget(hardware_tab)
        self.sidebar.addTab(hardware_scroll, 'SDR')

        scanner_tab = QtWidgets.QWidget()
        scanner_layout = QtWidgets.QVBoxLayout(scanner_tab)
        scanner_layout.setContentsMargins(6, 9, 6, 6)
        self.sidebar.addTab(scanner_tab, 'Scan')

        memory_tab = QtWidgets.QWidget()
        memories_layout = QtWidgets.QVBoxLayout(memory_tab)
        memories_layout.setContentsMargins(6, 9, 6, 6)
        self.sidebar.addTab(memory_tab, 'Geheugens')

        decoder_tab = QtWidgets.QWidget()
        decoder_layout = QtWidgets.QVBoxLayout(decoder_tab)
        decoder_layout.setContentsMargins(6, 9, 6, 6)
        decoder_scroll = QtWidgets.QScrollArea()
        decoder_scroll.setWidgetResizable(True)
        decoder_scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        decoder_scroll.setWidget(decoder_tab)
        self.sidebar.addTab(decoder_scroll, 'Decoders')

        spectrum_box = QtWidgets.QGroupBox('RF SPECTRUM  ·  Klik om af te stemmen · Filter slepen · Zoom met muiswiel')
        spectrum_l = QtWidgets.QVBoxLayout(spectrum_box)
        spectrum_l.setContentsMargins(6, 7, 6, 5)
        spectrum_controls = QtWidgets.QHBoxLayout()
        spectrum_controls.addWidget(QtWidgets.QLabel('Zoom:'))
        self.zoom_combo = QtWidgets.QComboBox()
        self.zoom_combo.addItems(['1×', '2×', '4×', '8×', '16×', '32×', '64×', '128×'])
        self.zoom_combo.setCurrentText('8×')
        self.zoom_combo.currentTextChanged.connect(self.zoom_changed)
        spectrum_controls.addWidget(self.zoom_combo)
        spectrum_controls.addWidget(QtWidgets.QLabel('FFT:'))
        self.fft_combo = QtWidgets.QComboBox()
        self.fft_combo.addItems(['2048', '4096', '8192', '16384'])
        self.fft_combo.setCurrentText('8192')
        self.fft_combo.currentTextChanged.connect(self.fft_changed)
        spectrum_controls.addWidget(self.fft_combo)
        zoom_reset = QtWidgets.QPushButton('Volledige band')
        zoom_reset.clicked.connect(lambda: self.zoom_combo.setCurrentText('1×'))
        spectrum_controls.addWidget(zoom_reset)
        spectrum_controls.addStretch(1)
        self.zoom_help = QtWidgets.QLabel('Muisklik = afstemmen · muiswiel = zoomen')
        self.zoom_help.setObjectName('status')
        spectrum_controls.addWidget(self.zoom_help)
        spectrum_l.addLayout(spectrum_controls)
        self.spectrum = pg.PlotWidget()
        self.spectrum.setLabel('bottom', 'Frequentie', units='MHz')
        self.spectrum.setLabel('left', 'RF', units='dBFS')
        self.spectrum.setYRange(-115, 5)
        self.spectrum.showGrid(x=True, y=True, alpha=0.16)
        self.spectrum.setMouseEnabled(x=True, y=False)
        self.curve = self.spectrum.plot(pen=pg.mkPen('#69F0E6', width=1.5))
        self.tune_marker = pg.InfiniteLine(pos=145.5, angle=90, movable=False,
                                           pen=pg.mkPen('#E9A860', width=1.2, style=QtCore.Qt.PenStyle.DashLine))
        self.spectrum.addItem(self.tune_marker)
        self.passband = pg.LinearRegionItem(values=(145.49375, 145.50625),
                                            movable=True,
                                            brush=pg.mkBrush(70, 214, 231, 48),
                                            pen=pg.mkPen('#36DCE6', width=1.4))
        self.passband.setZValue(-5)
        self.spectrum.addItem(self.passband)
        self.passband.sigRegionChangeFinished.connect(self.passband_changed)
        self.standby_marker = pg.InfiniteLine(pos=145.525, angle=90, movable=False,
                                              pen=pg.mkPen('#BC8BE6', width=1, style=QtCore.Qt.PenStyle.DotLine))
        self.spectrum.addItem(self.standby_marker)
        self.bw_annotation = pg.TextItem('BW 12.5 kHz', color='#5DDEEB', anchor=(0.5, 0))
        self.bw_annotation.setZValue(8)
        self.spectrum.addItem(self.bw_annotation)
        self.standby_annotation = pg.TextItem('B', color='#BC8BE6', anchor=(0.5, 0))
        self.standby_annotation.setZValue(8)
        self.spectrum.addItem(self.standby_annotation)
        self.spectrum.scene().sigMouseClicked.connect(self.spectrum_clicked)
        spectrum_l.addWidget(self.spectrum)
        left.addWidget(spectrum_box, 3)

        wf_box = QtWidgets.QGroupBox('WATERFALL  ·  Realtime IQ-signalen')
        wf_l = QtWidgets.QVBoxLayout(wf_box)
        wf_l.setContentsMargins(6, 7, 6, 5)
        wf_controls = QtWidgets.QHBoxLayout()
        wf_controls.addWidget(QtWidgets.QLabel('Snelheid:'))
        self.wf_speed = QtWidgets.QComboBox()
        self.wf_speed.addItems(['1×', '2×', '4×'])
        wf_controls.addWidget(self.wf_speed)
        wf_controls.addWidget(QtWidgets.QLabel('Kleuren:'))
        self.wf_colors = QtWidgets.QComboBox()
        self.wf_colors.addItems(['Thema', 'Grijs', 'Viridis'])
        self.wf_colors.currentTextChanged.connect(lambda _: self.update_waterfall_palette())
        wf_controls.addWidget(self.wf_colors)
        wf_controls.addWidget(QtWidgets.QLabel('Laag:'))
        self.wf_floor = QtWidgets.QSpinBox()
        self.wf_floor.setRange(-150, -30)
        self.wf_floor.setValue(-110)
        self.wf_floor.setSuffix(' dBFS')
        wf_controls.addWidget(self.wf_floor)
        wf_controls.addWidget(QtWidgets.QLabel('Hoog:'))
        self.wf_ceiling = QtWidgets.QSpinBox()
        self.wf_ceiling.setRange(-100, 20)
        self.wf_ceiling.setValue(-15)
        self.wf_ceiling.setSuffix(' dBFS')
        wf_controls.addWidget(self.wf_ceiling)
        wf_controls.addStretch(1)
        wf_l.addLayout(wf_controls)
        self.wf_plot = pg.PlotWidget()
        self.wf_plot.setLabel('bottom', 'Frequentie', units='MHz')
        self.wf_plot.setLabel('left', 'Tijd (nieuw boven)')
        self.wf_plot.setMouseEnabled(x=False, y=False)
        self.wf_plot.hideButtons()
        self.wf_image = pg.ImageItem()
        self.wf_plot.addItem(self.wf_image)
        self.wf_image.setImage(self.water, levels=(-110, -15), autoLevels=False)
        self.waterfall_marker = pg.InfiniteLine(pos=145.5, angle=90, movable=False,
                                                pen=pg.mkPen('#E9A860', width=1, style=QtCore.Qt.PenStyle.DashLine))
        self.wf_plot.addItem(self.waterfall_marker)
        self.standby_waterfall_marker = pg.InfiniteLine(pos=145.525, angle=90, movable=False,
                                          pen=pg.mkPen('#BC8BE6', width=1, style=QtCore.Qt.PenStyle.DotLine))
        self.wf_plot.addItem(self.standby_waterfall_marker)
        wf_l.addWidget(self.wf_plot)
        left.addWidget(wf_box, 3)

        device = QtWidgets.QGroupBox('Ontvanger & hardware')
        d = QtWidgets.QFormLayout(device)
        self.source = QtWidgets.QComboBox()
        self.source.addItems(['RTL-SDR', 'Airspy R2', 'Demo (geen hardware)'])
        self.source.currentTextChanged.connect(self.source_changed)
        d.addRow('SDR:', self.source)
        device_row = QtWidgets.QHBoxLayout()
        self.device_list = QtWidgets.QComboBox()
        self.device_list.setMinimumWidth(105)
        self.device_list.addItem('Automatisch (eerste SDR)', None)
        device_row.addWidget(self.device_list, 1)
        self.search_btn = QtWidgets.QPushButton('Zoek USB')
        self.search_btn.clicked.connect(self.refresh_hardware)
        device_row.addWidget(self.search_btn)
        d.addRow('Apparaat:', device_row)
        self.device_message = QtWidgets.QLabel('Zoek USB voor aangesloten ontvangers.')
        self.device_message.setWordWrap(True)
        self.device_message.setObjectName('status')
        d.addRow('', self.device_message)
        self.open_driver_folder_btn = QtWidgets.QPushButton('Open Airspy drivers-map')
        self.open_driver_folder_btn.clicked.connect(self.open_drivers_folder)
        d.addRow('', self.open_driver_folder_btn)
        self.rate = QtWidgets.QComboBox()
        self.rate.currentTextChanged.connect(self.refresh_vfo_info)
        d.addRow('Sample-rate:', self.rate)
        self.gain_auto = QtWidgets.QCheckBox('Automatisch / driverstandaard')
        self.gain_auto.setChecked(True)
        self.gain_auto.toggled.connect(self.gain_changed)
        d.addRow('RF gain:', self.gain_auto)
        self.gain = QtWidgets.QDoubleSpinBox()
        self.gain.setRange(0, 50)
        self.gain.setSingleStep(1)
        self.gain.setValue(20)
        self.gain.setSuffix(' dB')
        self.gain.setEnabled(False)
        self.gain.valueChanged.connect(self.gain_changed)
        d.addRow('Gain handmatig:', self.gain)
        s.addWidget(device)
        dsp_box = QtWidgets.QGroupBox('Audiofilters / DSP')
        dsp_layout = QtWidgets.QFormLayout(dsp_box)
        self.audio_agc = QtWidgets.QCheckBox('Audio-AGC inschakelen')
        self.audio_agc.setChecked(True)
        self.audio_agc.toggled.connect(lambda v: self.dsp_changed('agc', v))
        dsp_layout.addRow(self.audio_agc)
        notch_row = QtWidgets.QHBoxLayout()
        self.notch_enabled = QtWidgets.QCheckBox('Notch')
        self.notch_enabled.toggled.connect(lambda _: self.notch_changed())
        notch_row.addWidget(self.notch_enabled)
        self.notch_freq = QtWidgets.QSpinBox()
        self.notch_freq.setRange(150, 4500)
        self.notch_freq.setValue(1000)
        self.notch_freq.setSingleStep(50)
        self.notch_freq.setSuffix(' Hz')
        self.notch_freq.valueChanged.connect(lambda _: self.notch_changed())
        notch_row.addWidget(self.notch_freq, 1)
        dsp_layout.addRow(notch_row)
        self.noise_reduction = QtWidgets.QCheckBox('Spectrale ruisonderdrukking (experimenteel)')
        self.noise_reduction.toggled.connect(lambda v: self.dsp_changed('noise_reduction', v))
        dsp_layout.addRow(self.noise_reduction)
        self.eq_controls = []
        for label, default in [('Laag 180 Hz', 0), ('Midden 1 kHz', 0), ('Hoog 5,5 kHz', 0)]:
            control = QtWidgets.QSpinBox()
            control.setRange(-12, 12)
            control.setSuffix(' dB')
            control.setValue(default)
            control.valueChanged.connect(lambda _: self.equalizer_changed())
            self.eq_controls.append(control)
            dsp_layout.addRow('EQ ' + label + ':', control)
        self.eq_restore = QtWidgets.QPushButton('EQ vlak / reset')
        self.eq_restore.clicked.connect(lambda: [x.setValue(0) for x in self.eq_controls])
        dsp_layout.addRow(self.eq_restore)
        s.addWidget(dsp_box)
        calibration = QtWidgets.QGroupBox('RF meter · kalibratie')
        cal_row = QtWidgets.QFormLayout(calibration)
        self.s_calibrated = QtWidgets.QCheckBox('S/dBm-schatting tonen')
        self.s_calibrated.setToolTip('Alleen bruikbaar na kalibratie met bekend RF-niveau; S9-referentie is HF-conventie')
        cal_row.addRow(self.s_calibrated)
        self.dbm_reference = QtWidgets.QDoubleSpinBox()
        self.dbm_reference.setRange(-130, 70)
        self.dbm_reference.setValue(0)
        self.dbm_reference.setSuffix(' dBm bij 0 dBFS')
        cal_row.addRow('Referentie:', self.dbm_reference)
        s.addWidget(calibration)
        iq_box = QtWidgets.QGroupBox('IQ-opname & offline replay · CF32LE')
        iq_box_layout = QtWidgets.QVBoxLayout(iq_box)
        self.iq_record_btn = QtWidgets.QPushButton('● IQ-opname starten')
        self.iq_record_btn.setCheckable(True)
        self.iq_record_btn.setEnabled(False)
        self.iq_record_btn.toggled.connect(self.toggle_iq_recording)
        iq_box_layout.addWidget(self.iq_record_btn)
        self.iq_replay_btn = QtWidgets.QPushButton('▶ IQ-bestand afspelen…')
        self.iq_replay_btn.clicked.connect(self.open_iq_replay)
        iq_box_layout.addWidget(self.iq_replay_btn)
        iq_note = QtWidgets.QLabel('CF32LE IQ plus .json metadata; maximaal 2 GiB per bestand. Voor opnemen is 2,5 MSPS aanbevolen.')
        iq_note.setWordWrap(True)
        iq_note.setObjectName('status')
        iq_box_layout.addWidget(iq_note)
        s.addWidget(iq_box)
        rds_box = QtWidgets.QGroupBox('RDS · WFM zenderinformatie')
        rds_layout = QtWidgets.QVBoxLayout(rds_box)
        self.rds_toggle = QtWidgets.QCheckBox('RDS ontvangen via redsea.exe (alleen WFM)')
        self.rds_toggle.toggled.connect(self.toggle_rds)
        rds_layout.addWidget(self.rds_toggle)
        redsea_row = QtWidgets.QHBoxLayout()
        self.redsea_path = QtWidgets.QLineEdit(str(self.settings.value('redsea_path','')))
        self.redsea_path.setPlaceholderText('redsea.exe in decoders/bin of kies het .exe-bestand')
        redsea_row.addWidget(self.redsea_path,1)
        redsea_browse = QtWidgets.QPushButton('...')
        redsea_browse.clicked.connect(self.browse_redsea)
        redsea_row.addWidget(redsea_browse)
        rds_layout.addLayout(redsea_row)
        self.rds_display = QtWidgets.QLabel('PS: —   ·   PI: —\nRadiotekst: —')
        self.rds_display.setWordWrap(True)
        rds_layout.addWidget(self.rds_display)
        rds_info = QtWidgets.QLabel('RDS komt uit de 57-kHz FM-multiplex, niet uit de luidsprekeraudio. Extern redsea-programma vereist.')
        rds_info.setWordWrap(True)
        rds_info.setObjectName('status')
        rds_layout.addWidget(rds_info)
        s.addWidget(rds_box)
        s.addStretch()

        scanbox = QtWidgets.QGroupBox('Geheugenscanner')
        scan_col = QtWidgets.QVBoxLayout(scanbox)
        self.scan_toggle = QtWidgets.QCheckBox('Scan geheugenkanalen (SQL-gestuurd)')
        self.scan_toggle.setEnabled(False)
        self.scan_toggle.toggled.connect(self.scanner_changed)
        scan_col.addWidget(self.scan_toggle)
        self.scan_info = QtWidgets.QLabel('Nog geen geheugenkanalen opgeslagen.')
        self.scan_info.setWordWrap(True)
        self.scan_info.setObjectName('status')
        scan_col.addWidget(self.scan_info)
        scan_form = QtWidgets.QFormLayout()
        self.scan_type = QtWidgets.QComboBox()
        self.scan_type.addItems(['Geheugenkanalen', 'Frequentiebereik'])
        scan_form.addRow('Scanmodus:', self.scan_type)
        self.scan_group = QtWidgets.QComboBox()
        self.scan_group.addItems([ALL_GROUPS, *self.memory_group_names])
        self.scan_group.currentTextChanged.connect(self.scan_group_changed)
        scan_form.addRow('Scangroep:', self.scan_group)
        self.choose_scan_btn = QtWidgets.QPushButton('Kies scankanalen (selecteer bijvoorbeeld 10 van 20)')
        self.choose_scan_btn.clicked.connect(self.choose_scan_channels)
        scan_col.addWidget(self.choose_scan_btn)
        self.scan_start = QtWidgets.QDoubleSpinBox()
        self.scan_start.setRange(.01, 2000)
        self.scan_start.setDecimals(6)
        self.scan_start.setValue(144.0)
        self.scan_start.setSuffix(' MHz')
        self.scan_end = QtWidgets.QDoubleSpinBox()
        self.scan_end.setRange(.01, 2000)
        self.scan_end.setDecimals(6)
        self.scan_end.setValue(146.0)
        self.scan_end.setSuffix(' MHz')
        self.scan_step = QtWidgets.QSpinBox()
        self.scan_step.setRange(100, 1000000)
        self.scan_step.setSingleStep(500)
        self.scan_step.setValue(12500)
        self.scan_step.setSuffix(' Hz')
        for label, control in [('Van:',self.scan_start),('Tot:',self.scan_end),('Stap:',self.scan_step)]:
            scan_form.addRow(label, control)
        self.scan_dwell = QtWidgets.QSpinBox()
        self.scan_dwell.setRange(150,30000)
        self.scan_dwell.setValue(700)
        self.scan_dwell.setSuffix(' ms')
        self.scan_hold = QtWidgets.QSpinBox()
        self.scan_hold.setRange(0,120000)
        self.scan_hold.setValue(1800)
        self.scan_hold.setSuffix(' ms')
        scan_form.addRow('Dwell:', self.scan_dwell)
        scan_form.addRow('Hold:', self.scan_hold)
        scan_col.addLayout(scan_form)
        self.scan_type.currentTextChanged.connect(self.scan_type_changed)
        self.scan_type_changed()
        show_memories = QtWidgets.QPushButton('Bekijk geheugenkanalen')
        show_memories.clicked.connect(lambda: self.sidebar.setCurrentWidget(memory_tab))
        scan_col.addWidget(show_memories)
        scanner_layout.addWidget(scanbox)
        scan_note = QtWidgets.QLabel('De scanner gebruikt de opgeslagen kanalen. Schakel de ontvanger in voordat je de scan start.')
        scan_note.setWordWrap(True)
        scanner_layout.addWidget(scan_note)
        scanner_layout.addStretch()

        memory = QtWidgets.QGroupBox('Geheugenkanalen')
        m = QtWidgets.QVBoxLayout(memory)
        group_row = QtWidgets.QHBoxLayout()
        self.mem_group = QtWidgets.QComboBox()
        self.mem_group.addItem('Alle groepen')
        self.mem_group.currentTextChanged.connect(self.memory_group_changed)
        group_row.addWidget(QtWidgets.QLabel('Groep:'))
        group_row.addWidget(self.mem_group, 1)
        m.addLayout(group_row)
        group_buttons = QtWidgets.QHBoxLayout()
        for label, method in [('+ Groep', self.create_memory_group),
                              ('Hernoem', self.rename_memory_group),
                              ('Wis groep', self.delete_memory_group)]:
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(method)
            group_buttons.addWidget(button)
        m.addLayout(group_buttons)
        self.memlist = QtWidgets.QListWidget()
        self.memlist.setMinimumHeight(148)
        self.memlist.itemDoubleClicked.connect(lambda _: self.edit_memory())
        m.addWidget(self.memlist)
        r = QtWidgets.QHBoxLayout()
        for label, method in [('+ Kanaal', self.add_memory), ('Bewerk', self.edit_memory),
                              ('Afstemmen', self.goto_memory), ('Verwijder', self.delete_memory)]:
            b = QtWidgets.QPushButton(label)
            b.clicked.connect(method)
            r.addWidget(b)
        m.addLayout(r)
        shortcuts_note = QtWidgets.QLabel('F1–F8: direct geheugen met toegewezen sneltoets oproepen')
        shortcuts_note.setWordWrap(True)
        shortcuts_note.setObjectName('status')
        m.addWidget(shortcuts_note)
        memories_layout.addWidget(memory, 1)
        self.shortcuts = []
        for number in range(1, 9):
            shortcut = QtGui.QShortcut(QtGui.QKeySequence(f'F{number}'), self)
            shortcut.activated.connect(lambda number=number: self.goto_shortcut(number))
            self.shortcuts.append(shortcut)

        # Passive DIGITAL AUTO monitor: RF candidates are NOT identified protocols.
        auto_box = QtWidgets.QGroupBox('DIGITAL AUTO · RF-kandidaten')
        auto_l = QtWidgets.QVBoxLayout(auto_box)
        self.auto_toggle = QtWidgets.QCheckBox('⚡ AUTO monitor inschakelen')
        self.auto_toggle.setToolTip('Zoekt opvallende signalen in het ontvangen spectrum. Herkent nog geen protocol uit FFT alleen.')
        self.auto_toggle.toggled.connect(self.toggle_rf_monitor)
        auto_l.addWidget(self.auto_toggle)
        sens = QtWidgets.QHBoxLayout()
        sens.addWidget(QtWidgets.QLabel('Drempel boven ruis:'))
        self.auto_sensitivity = QtWidgets.QSpinBox()
        self.auto_sensitivity.setRange(12, 35)
        self.auto_sensitivity.setValue(17)
        self.auto_sensitivity.setSuffix(' dB')
        self.auto_sensitivity.valueChanged.connect(self.update_auto_sensitivity)
        sens.addWidget(self.auto_sensitivity)
        auto_l.addLayout(sens)
        self.auto_info = QtWidgets.QLabel('Uit: geen automatische RF-analyse. Protocolbevestiging vereist een decoder.')
        self.auto_info.setWordWrap(True)
        self.auto_info.setObjectName('status')
        auto_l.addWidget(self.auto_info)
        self.auto_candidates = QtWidgets.QTreeWidget()
        self.auto_candidates.setHeaderLabels(['MHz','RF boven ruis','Breedte','Status'])
        self.auto_candidates.setRootIsDecorated(False)
        self.auto_candidates.setAlternatingRowColors(True)
        self.auto_candidates.setMinimumHeight(155)
        self.auto_candidates.setColumnWidth(0,85)
        self.auto_candidates.setColumnWidth(1,100)
        self.auto_candidates.setColumnWidth(2,70)
        self.auto_candidates.itemDoubleClicked.connect(lambda _: self.tune_auto_candidate())
        auto_l.addWidget(self.auto_candidates)
        act = QtWidgets.QHBoxLayout()
        self.auto_tune_btn = QtWidgets.QPushButton('↗ Afstemmen')
        self.auto_tune_btn.clicked.connect(self.tune_auto_candidate)
        act.addWidget(self.auto_tune_btn)
        self.auto_scan_btn = QtWidgets.QPushButton('Scan + monitor')
        self.auto_scan_btn.clicked.connect(self.start_auto_scan)
        act.addWidget(self.auto_scan_btn)
        auto_l.addLayout(act)
        act2 = QtWidgets.QHBoxLayout()
        self.auto_verify_btn = QtWidgets.QPushButton('▶ Controleren met DSD-neo')
        self.auto_verify_btn.setToolTip('Stopt eerst de gewone ontvangst en opent de externe decoder op het geselecteerde kanaal.')
        self.auto_verify_btn.clicked.connect(self.verify_auto_candidate)
        act2.addWidget(self.auto_verify_btn)
        self.auto_export_btn = QtWidgets.QPushButton('Exporteer CSV')
        self.auto_export_btn.clicked.connect(self.export_auto_candidates)
        act2.addWidget(self.auto_export_btn)
        auto_l.addLayout(act2)
        self.auto_clear_btn = QtWidgets.QPushButton('Wis RF-lijst')
        self.auto_clear_btn.clicked.connect(self.clear_auto_candidates)
        auto_l.addWidget(self.auto_clear_btn)
        auto_note = QtWidgets.QLabel('RF-kandidaat ≠ digitaal protocol. Alleen daadwerkelijke DSD-neo synchronisatie/frames bevestigen een protocol. Dubbelklik om af te stemmen.')
        auto_note.setWordWrap(True)
        auto_note.setObjectName('status')
        auto_l.addWidget(auto_note)
        decoder_layout.addWidget(auto_box)

        decoderbox = QtWidgets.QGroupBox('Externe digitale decoders')
        dec = QtWidgets.QVBoxLayout(decoderbox)
        self.decoder_combo = QtWidgets.QComboBox()
        self.decoder_combo.addItems([item.label for item in DECODERS])
        self.decoder_combo.currentTextChanged.connect(self.decoder_changed)
        dec.addWidget(self.decoder_combo)
        self.auto_digital_btn = QtWidgets.QPushButton('⚡ Automatische digitale spraakherkenning (DSD-neo)')
        self.auto_digital_btn.setToolTip('Start het externe DSD-neo AUTO-profiel. Zonder decoder is geen protocolherkenning mogelijk.')
        self.auto_digital_btn.clicked.connect(self.start_digital_auto)
        dec.addWidget(self.auto_digital_btn)
        self.rf_hint = QtWidgets.QLabel('RF-analyse: wacht op spectrum...')
        self.rf_hint.setWordWrap(True)
        self.rf_hint.setObjectName('status')
        dec.addWidget(self.rf_hint)
        self.decoder_info = QtWidgets.QLabel('')
        self.decoder_info.setWordWrap(True)
        self.decoder_info.setObjectName('status')
        dec.addWidget(self.decoder_info)
        tune = QtWidgets.QHBoxLayout()
        self.preset_btn = QtWidgets.QPushButton('↗ Stem op modefrequentie af')
        self.preset_btn.clicked.connect(self.tune_decoder_preset)
        tune.addWidget(self.preset_btn)
        dec.addLayout(tune)
        self.decoder_availability = QtWidgets.QLabel('')
        self.decoder_availability.setWordWrap(True)
        dec.addWidget(self.decoder_availability)
        self.decoder_project_btn = QtWidgets.QPushButton('↗ Project / download van externe decoder')
        self.decoder_project_btn.setToolTip('Opent alleen de projectwebsite; installeert niets automatisch.')
        self.decoder_project_btn.clicked.connect(self.open_decoder_project)
        dec.addWidget(self.decoder_project_btn)
        dec.addWidget(QtWidgets.QLabel('Uitvoerbaar programma:'))
        self.exec_name = QtWidgets.QLineEdit()
        exe_picker = QtWidgets.QHBoxLayout()
        exe_picker.addWidget(self.exec_name, 1)
        browse = QtWidgets.QPushButton('…')
        browse.setToolTip('Selecteer de executable van de decoder')
        browse.clicked.connect(self.browse_decoder_exe)
        exe_picker.addWidget(browse)
        dec.addLayout(exe_picker)
        dec.addWidget(QtWidgets.QLabel('Argumenten (aanpasbaar):'))
        self.decoder_args = QtWidgets.QLineEdit()
        dec.addWidget(self.decoder_args)
        dr = QtWidgets.QHBoxLayout()
        self.decoder_btn = QtWidgets.QPushButton('▶ Decoder starten')
        self.decoder_btn.clicked.connect(self.start_decoder)
        dr.addWidget(self.decoder_btn)
        self.decoder_stop = QtWidgets.QPushButton('■ Stop')
        self.decoder_stop.clicked.connect(self.stop_decoder)
        self.decoder_stop.setEnabled(False)
        dr.addWidget(self.decoder_stop)
        dec.addLayout(dr)
        info = QtWidgets.QLabel('Externe decoders worden niet meegeleverd. Voor sommige modes zijn extra programma’s en een eigen SDR-/audio-invoer nodig.')
        info.setWordWrap(True)
        info.setObjectName('status')
        dec.addWidget(info)
        decoder_layout.addWidget(decoderbox)
        event_box = QtWidgets.QGroupBox('Gedecodeerde berichten (uit externe decoder)')
        events_l = QtWidgets.QVBoxLayout(event_box)
        self.event_table = QtWidgets.QTreeWidget()
        self.event_table.setHeaderLabels(['Tijd', 'Protocol / bron', 'Bericht'])
        self.event_table.setRootIsDecorated(False)
        self.event_table.setAlternatingRowColors(True)
        self.event_table.setMinimumHeight(155)
        self.event_table.setColumnWidth(0, 68)
        self.event_table.setColumnWidth(1, 125)
        self.event_filter = QtWidgets.QLineEdit()
        self.event_filter.setPlaceholderText('Filter ontvangen decoderberichten...')
        self.event_filter.textChanged.connect(self.filter_decoder_events)
        events_l.addWidget(self.event_filter)
        events_l.addWidget(self.event_table)
        self.event_counter = QtWidgets.QLabel('0 decoderberichten ontvangen')
        self.event_counter.setObjectName('status')
        events_l.addWidget(self.event_counter)
        erow = QtWidgets.QHBoxLayout()
        self.export_events_btn = QtWidgets.QPushButton('Exporteer CSV')
        self.export_events_btn.clicked.connect(self.export_decoder_events)
        erow.addWidget(self.export_events_btn)
        export_json = QtWidgets.QPushButton('Exporteer JSON')
        export_json.clicked.connect(self.export_decoder_json)
        erow.addWidget(export_json)
        clear_btn = QtWidgets.QPushButton('Wissen')
        clear_btn.clicked.connect(self.clear_decoder_events)
        erow.addWidget(clear_btn)
        events_l.addLayout(erow)
        decoder_layout.addWidget(event_box)
        decoder_layout.addStretch()
        self.decoder_changed()

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(500)
        self.log.setMaximumHeight(88)
        self.log.setMinimumHeight(55)
        self.log.setPlaceholderText('Status en decoder-output verschijnen hier...')
        outer.addWidget(self.log)
        self.status_bar = QtWidgets.QLabel('Gereed — SDR Studio RX by M@rcello. Kies een ontvanger en druk op ONTVANGEN.')
        self.status_bar.setObjectName('status')
        self.status_bar.setMinimumWidth(0)
        self.status_bar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                                      QtWidgets.QSizePolicy.Policy.Fixed)
        self._full_status_text = self.status_bar.text()
        outer.addWidget(self.status_bar)

    def apply_theme(self, theme):
        """Recolor all Qt widgets and both live plots; preserve tuning and IQ stream."""
        c = colors(theme)
        self.theme = theme
        app = QtWidgets.QApplication.instance()
        app.setStyleSheet(build_stylesheet(theme))
        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor(c['bg']))
        palette.setColor(QtGui.QPalette.ColorRole.WindowText, QtGui.QColor(c['text']))
        palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(c['input']))
        palette.setColor(QtGui.QPalette.ColorRole.Text, QtGui.QColor(c['text']))
        palette.setColor(QtGui.QPalette.ColorRole.Button, QtGui.QColor(c['button']))
        palette.setColor(QtGui.QPalette.ColorRole.ButtonText, QtGui.QColor(c['text']))
        palette.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor(c['selected']))
        palette.setColor(QtGui.QPalette.ColorRole.HighlightedText, QtGui.QColor(c['text']))
        app.setPalette(palette)
        self.brand.setText(f'<b style="font-size:18px;color:{c["text"]}">SDR Studio '
                           f'<span style="color:{c["accent"]}">RX</span></b> '
                           f'<span style="color:{c["muted"]};font-size:11px">by M@rcello  ·  v0.8 beta</span>')
        self.theme_button.setText('☀ Licht' if theme == 'dark' else '☾ Donker')
        self.theme_button.setToolTip('Wissel naar licht uiterlijk (Ctrl+T)' if theme == 'dark'
                                     else 'Wissel naar donker uiterlijk (Ctrl+T)')
        self.update_waterfall_palette()
        self.curve.setPen(pg.mkPen(c['spectrum'], width=1.4))
        self.tune_marker.setPen(pg.mkPen(c['marker'], width=1.2, style=QtCore.Qt.PenStyle.DashLine))
        self.waterfall_marker.setPen(pg.mkPen(c['marker'], width=1, style=QtCore.Qt.PenStyle.DashLine))
        self.passband.setBrush(pg.mkBrush(QtGui.QColor(33, 185, 208, 48)))
        for boundary in self.passband.lines:
            boundary.setPen(pg.mkPen(c['accent'], width=1.4))
        self.bw_annotation.setColor(c['accent'])
        for plot in (self.spectrum, self.wf_plot):
            plot.setBackground(c['plot_bg'])
            for side in ('bottom', 'left'):
                axis = plot.getAxis(side)
                axis.setPen(pg.mkPen(c['plot_fg']))
                axis.setTextPen(pg.mkPen(c['plot_fg']))
        self.settings.setValue('theme', theme)

    def update_waterfall_palette(self):
        choice = self.wf_colors.currentText() if hasattr(self, 'wf_colors') else 'Thema'
        if choice == 'Grijs':
            palette = ('#030303', '#303030', '#626262', '#959595', '#c3c3c3', '#ffffff')
        elif choice == 'Viridis':
            palette = ('#440154', '#443983', '#31688e', '#35b779', '#90d743', '#fde725')
        else:
            palette = colors(self.theme)['waterfall']
        lut = pg.ColorMap([0,.22,.42,.62,.82,1], palette).getLookupTable(nPts=256)
        self.wf_image.setLookupTable(lut)

    def toggle_theme(self):
        self.apply_theme('light' if self.theme == 'dark' else 'dark')

    def _load_vfos(self):
        for which in ('A', 'B'):
            v = self.vfos.vfos[which]
            try:
                freq = int(self.settings.value(f'vfo/{which}/frequency', v.frequency_hz))
                mode = str(self.settings.value(f'vfo/{which}/mode', v.mode))
                bw = int(self.settings.value(f'vfo/{which}/bandwidth', v.bandwidth_hz))
                sql = int(self.settings.value(f'vfo/{which}/squelch', v.squelch_dbfs))
                shift = int(self.settings.value(f'vfo/{which}/shift', 0))
                if mode not in MODES:
                    mode = 'NFM'
                if not BANDWIDTHS[mode][0] <= bw <= BANDWIDTHS[mode][-1]:
                    bw = DEFAULT_BW[mode]
                if 10_000 <= freq <= 2_000_000_000:
                    v.frequency_hz = freq
                v.mode = mode
                v.bandwidth_hz = bw
                v.squelch_dbfs = max(-100, min(0, sql))
                v.passband_shift_hz = max(-100_000, min(100_000, shift))
            except (TypeError, ValueError):
                continue
        active = self.settings.value('vfo/active', 'A')
        self.vfos.active = active if active in ('A','B') else 'A'

    def _restore_vfo_controls(self):
        state = self.vfos.current()
        self._vfo_loading = True
        try:
            for control, setting in ((self.freq, lambda: self.freq.setValue(state.frequency_hz/1e6)),
                                     (self.mode, lambda: self.mode.setCurrentText(state.mode)),
                                     (self.sql, lambda: self.sql.setValue(state.squelch_dbfs))):
                control.blockSignals(True)
                setting()
                control.blockSignals(False)
            self._set_bandwidth_limits(state.mode)
            self.bandwidth_spin.setValue(state.bandwidth_hz)
            self.pbt_shift.setValue(state.passband_shift_hz)
            self.sql_label.setText(f'{state.squelch_dbfs} dBFS')
            self.tune_marker.setValue(state.frequency_hz/1e6)
            self.waterfall_marker.setValue(state.frequency_hz/1e6)
        finally:
            self._vfo_loading = False

    def _save_vfos(self):
        for key, vfo in self.vfos.vfos.items():
            for name, value in (('frequency',vfo.frequency_hz),('mode',vfo.mode),
                                ('bandwidth',vfo.bandwidth_hz),('squelch',vfo.squelch_dbfs),('shift',vfo.passband_shift_hz)):
                self.settings.setValue(f'vfo/{key}/{name}', value)
        self.settings.setValue('vfo/active', self.vfos.active)

    def get_bandwidth(self):
        return self.bandwidth_spin.value()

    def _update_vfo_labels(self):
        active = self.vfos.active
        other = 'B' if active == 'A' else 'A'
        self.vfo_a_btn.setChecked(active == 'A')
        self.vfo_b_btn.setChecked(active == 'B')
        current, standby = self.vfos.current(), self.vfos.standby()
        self.vfo_copy_btn.setText(f'{active} → {other}')
        self.standby_label.setText(f'{other}: {standby.frequency_hz / 1e6:.6f} MHz  ·  '
                                   f'{standby.mode}  ·  BW {standby.bandwidth_hz:g} Hz')
        self.standby_marker.setValue(standby.frequency_hz / 1e6)
        self.standby_annotation.setText(other)
        self.standby_annotation.setPos(standby.frequency_hz / 1e6, -25)
        self.standby_waterfall_marker.setValue(standby.frequency_hz / 1e6)
        self.freq_label.setText(f'{current.frequency_hz / 1e6:.6f}')

    def _sync_passband(self):
        if not hasattr(self, 'passband'):
            return
        self._syncing_region = True
        try:
            mhz = (self.get_freq() + self.pbt_shift.value())/1e6
            half = self.get_bandwidth()/2e6
            self.passband.setRegion((mhz-half, mhz+half))
            self.bw_annotation.setText(f'BW {self.get_bandwidth()/1000:g} kHz · PBT {self.pbt_shift.value():+d} Hz')
            self.bw_annotation.setPos(mhz, -5)
        finally:
            self._syncing_region = False

    def passband_changed(self):
        if self._syncing_region:
            return
        low, high = self.passband.getRegion()
        if high <= low:
            return
        bw = round((high-low)*1e6)
        limits = BANDWIDTHS[self.mode.currentText()]
        bw = max(limits[0], min(limits[-1], bw))
        target_shift = int(round((low + high)/2 * 1e6 - self.get_freq()))
        self.bandwidth_spin.setValue(bw)
        self.pbt_shift.setValue(max(-100_000, min(100_000, target_shift)))
        self._sync_passband()

    def bandwidth_changed(self, value):
        if self._vfo_loading:
            return
        self.vfos.current().bandwidth_hz = int(value)
        self._sync_passband()
        if self.worker and self.worker.is_alive():
            self.worker.command('bandwidth', int(value))

    def passband_shift_changed(self, value):
        if self._vfo_loading:
            return
        self.vfos.current().passband_shift_hz = int(value)
        self._sync_passband()
        self.dsp_changed('passband_shift', int(value))

    def equalizer_changed(self):
        gains = tuple(x.value() for x in self.eq_controls)
        self.dsp_changed('equalizer', gains)

    def select_vfo(self, name):
        if name == self.vfos.active:
            return
        previous = self.vfos.active
        self.vfos.select(name)
        state = self.vfos.current()
        self._vfo_loading = True
        try:
            for widget, setter, value in ((self.freq, self.freq.setValue, state.frequency_hz/1e6),
                                          (self.mode, self.mode.setCurrentText, state.mode),
                                          (self.sql, self.sql.setValue, state.squelch_dbfs)):
                widget.blockSignals(True)
                setter(value)
                widget.blockSignals(False)
            self._set_bandwidth_limits(state.mode)
            self.bandwidth_spin.setValue(state.bandwidth_hz)
            self.pbt_shift.setValue(state.passband_shift_hz)
        finally:
            self._vfo_loading = False
        self._step_anchor_hz, self._step_count = state.frequency_hz, 0
        self.sql_label.setText(f'{state.squelch_dbfs} dBFS')
        # Update plots and labels locally. Do NOT call frequency_changed(),
        # which would send a separate retune command before the mode/BW.
        self.tune_marker.setValue(state.frequency_hz / 1e6)
        self.waterfall_marker.setValue(state.frequency_hz / 1e6)
        self._sync_passband()
        self._update_vfo_labels()
        self.refresh_vfo_info()
        if self.worker and self.worker.is_alive():
            if self.scan_toggle.isChecked():
                self.scan_toggle.blockSignals(True)
                self.scan_toggle.setChecked(False)
                self.scan_toggle.blockSignals(False)
            self._vfo_request_seq += 1
            self.worker.command('vfo', {
                'name': name, 'previous': previous, 'seq': self._vfo_request_seq,
                'frequency_hz': state.frequency_hz, 'mode': state.mode,
                'bandwidth_hz': state.bandwidth_hz,
                'passband_shift_hz': state.passband_shift_hz,
                'squelch_dbfs': state.squelch_dbfs})
        self.on_status(f'VFO {name} gekozen; hardware stemt af zonder te stoppen.')

    def on_tune_result(self, response):
        request = response['request']
        # Ignore stale notifications after a rapid A/B/A switch.
        if request.get('seq') != self._vfo_request_seq:
            return
        if response['success']:
            self.on_status(f"VFO {request['name']} actief: "
                           f"{response['frequency_hz']/1e6:.6f} MHz")
            return
        if self.vfos.active == request['name']:
            self.vfos.select(request['previous'])
            self._restore_vfo_controls()
            self._step_anchor_hz, self._step_count = self.get_freq(), 0
            self._sync_passband()
            self._update_vfo_labels()
            self.refresh_vfo_info()
        self.on_status(f"VFO wisselen niet gelukt: {response['error']} (RX blijft actief)")

    def swap_vfo(self):
        self.select_vfo('B' if self.vfos.active == 'A' else 'A')

    def copy_vfo(self):
        self.vfos.copy_to_other()
        self._update_vfo_labels()
        self.on_status(f'VFO {self.vfos.active} naar stand-by gekopieerd.')

    def _set_bandwidth_limits(self, mode):
        options = BANDWIDTHS[mode]
        self.bandwidth_spin.blockSignals(True)
        self.bandwidth_spin.setRange(options[0], options[-1])
        self.bandwidth_spin.setSingleStep(100 if mode in ('CW','USB','LSB') else 500)
        self.bandwidth_spin.blockSignals(False)

    def fft_changed(self, value):
        if self.worker and self.worker.is_alive():
            self.worker.command('fft_size', int(value))

    def zoom_changed(self, *_):
        if self._last_plot_rate is not None:
            self._set_plot_range(self._last_plot_center, self._last_plot_rate)

    def _set_plot_range(self, center_hz, rate_hz):
        zoom = int(self.zoom_combo.currentText().replace('×', ''))
        center = center_hz/1e6
        half = rate_hz/2e6/zoom
        # The waterfall and spectrum always display the same frequency range.
        self.spectrum.setXRange(center-half, center+half, padding=0)
        self.wf_plot.setXRange(center-half, center+half, padding=0)

    def dsp_changed(self, option, value):
        if self.worker and self.worker.is_alive():
            self.worker.command(option, value)

    def notch_changed(self):
        hz = self.notch_freq.value() if self.notch_enabled.isChecked() else 0
        self.dsp_changed('notch', hz)

    def scan_type_changed(self, *_):
        range_enabled = self.scan_type.currentText() == 'Frequentiebereik'
        for w in (self.scan_start, self.scan_end, self.scan_step):
            w.setEnabled(range_enabled)
        self.scan_group.setEnabled(not range_enabled)
        self.choose_scan_btn.setEnabled(not range_enabled and bool(self.memories))
        if self.scan_toggle.isChecked():
            self.scanner_changed(True)

    def scan_group_changed(self, group):
        # Keep the Geheugens-tab and scanner on the same group.
        if hasattr(self, 'mem_group') and self.mem_group.currentText() != group:
            self.mem_group.setCurrentText(group)
        self.update_scan_summary()

    def update_scan_summary(self):
        if not hasattr(self, 'scan_info') or not hasattr(self, 'scan_group'):
            return
        group = self.scan_group.currentText()
        selected, total = scan_counts(self.memories, group)
        self.scan_info.setText(f'Groep {group}: {selected} van {total} kanalen geselecteerd voor scannen.'
                               if total else f'Groep {group}: geen kanalen opgeslagen.')
        if hasattr(self, 'choose_scan_btn'):
            self.choose_scan_btn.setText(f'Kies scankanalen ({selected}/{total})')
            self.choose_scan_btn.setEnabled(bool(total) and self.scan_type.currentText() == 'Geheugenkanalen')

    def choose_scan_channels(self):
        group = self.scan_group.currentText()
        current = group_members(self.memories, group)
        if not current:
            QtWidgets.QMessageBox.information(self, 'Groepsscanner', 'Geen frequenties in de gekozen groep.')
            return
        dialog = ScanSelectionDialog(self, group, current)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        flags = {id(memory): enabled for memory, enabled in dialog.selections()}
        updated = [dict(memory, scan_enabled=flags.get(id(memory),
                           memory.get('scan_enabled', True) is not False))
                   for memory in self.memories]
        try:
            save_memories(updated)
        except OSError as exc:
            QtWidgets.QMessageBox.warning(self, 'Scankanalen', f'Kan selectie niet bewaren: {exc}')
            return
        self.memories = updated
        self.refresh_memories()
        if self.scan_toggle.isChecked() and self.scan_type.currentText() == 'Geheugenkanalen':
            self.scanner_changed(True)
        selected, total = scan_counts(self.memories, group)
        self.on_status(f'Groepsscanner {group}: {selected} van {total} kanalen geselecteerd.')

    def scan_configuration(self):
        if self.scan_type.currentText() == 'Geheugenkanalen':
            items = scan_candidates(self.memories, self.scan_group.currentText())
        else:
            if self.source.currentText() == 'Airspy R2' and (self.scan_start.value() < 24 or self.scan_end.value() > 1750):
                raise ValueError('Airspy R2 ondersteunt hier alleen 24–1750 MHz')
            frequencies = frequency_range(round(self.scan_start.value()*1e6),
                                          round(self.scan_end.value()*1e6),
                                          self.scan_step.value())
            items = [{'frequency': hz, 'mode': self.mode.currentText()} for hz in frequencies]
        if not items:
            raise ValueError('Geen scankanalen geselecteerd. Gebruik Kies scankanalen of kies Frequentiebereik.')
        return {'items': items, 'dwell_ms': self.scan_dwell.value(),
                'hold_ms': self.scan_hold.value()}

    def filter_decoder_events(self, value):
        needle = value.casefold().strip()
        for i in range(self.event_table.topLevelItemCount()):
            item = self.event_table.topLevelItem(i)
            item.setHidden(needle not in ' '.join(item.text(j) for j in range(3)).casefold())

    def clear_decoder_events(self):
        self.event_table.clear()
        self._event_count = 0
        self.event_counter.setText('0 decoderberichten ontvangen')

    def export_decoder_json(self):
        if not self.event_table.topLevelItemCount():
            self.on_status('Geen decoderberichten om te exporteren.')
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Exporteer berichten',
                                                         'decoder-berichten.json', 'JSON (*.json)')
        if not path:
            return
        import json
        records = []
        for i in range(self.event_table.topLevelItemCount()):
            item = self.event_table.topLevelItem(i)
            records.append({'tijd':item.text(0),'protocol':item.text(1),
                            'bericht':item.text(2),'raw':item.toolTip(2)})
        try:
            Path(path).write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
            self.on_status(f'Decoderberichten geëxporteerd: {path}')
        except OSError as exc:
            self.on_status(f'FOUT: JSON-export mislukt: {exc}')

    def source_changed(self, *_):
        selected = self.source.currentText()
        self.rate.clear()
        if selected == 'Airspy R2':
            self.rate.addItems(['2.5 MSPS', '10 MSPS'])
            self.gain.setRange(0, 21)
            self.gain.setValue(12)
            self.gain.setSuffix(' stap')
            self.freq.setRange(24.0, 1750.0)
        else:
            self.rate.addItems(['2.4 MSPS', '2.048 MSPS'])
            self.gain.setRange(0, 50)
            self.gain.setSuffix(' dB')
            self.freq.setRange(0.01, 2_000)
        self.refresh_hardware()
        self.refresh_vfo_info()
        self.decoder_changed()

    def refresh_hardware(self):
        kind = self.source.currentText()
        self.device_list.clear()
        self.device_list.addItem('Automatisch (eerste SDR)', None)
        radios, message = discover(kind)
        for radio in radios:
            if kind != 'Demo (geen hardware)':
                self.device_list.addItem(radio.label, encode_device_id(radio.identifier))
        self.device_message.setText(message)
        self.on_status(message)

    def get_rate(self):
        return int(float(self.rate.currentText().split()[0]) * 1_000_000)

    def get_freq(self):
        return int(round(self.freq.value() * 1e6))

    def get_gain(self):
        return None if self.gain_auto.isChecked() else self.gain.value()

    def step_changed(self, name):
        if not name:
            return
        self.settings.setValue('frequency_step', name)
        self._step_anchor_hz = self.get_freq()
        self._step_count = 0
        self.freq.setSingleStep(float(tuning_step_hz(name)) / 1_000_000)
        self.refresh_vfo_info()

    def tune_by_steps(self, steps):
        """Retune in accurate Hz increments, including exact 25/3 kHz steps."""
        if not steps or not self.freq.isEnabled():
            return
        self.freq.interpretText()  # Commit partially edited frequency first.
        current = self.get_freq()
        if current != tuned_frequency_hz(self._step_anchor_hz,
                                         self.step_combo.currentText(), self._step_count):
            self._step_anchor_hz, self._step_count = current, 0
        next_count = self._step_count + int(steps)
        target_hz = tuned_frequency_hz(self._step_anchor_hz,
                                        self.step_combo.currentText(), next_count)
        low = round(self.freq.minimum() * 1_000_000)
        high = round(self.freq.maximum() * 1_000_000)
        if not (low <= target_hz <= high):
            return
        self._step_count = next_count
        self._internal_tune = True
        try:
            self.freq.setValue(target_hz / 1_000_000)
        finally:
            self._internal_tune = False

    def frequency_changed(self, *_):
        if not self._internal_tune:
            self._step_anchor_hz = self.get_freq()
            self._step_count = 0
        if not self._vfo_loading:
            self.vfos.current().frequency_hz = self.get_freq()
        self._update_vfo_labels()
        self._sync_passband()
        self.tune_marker.setValue(self.freq.value())
        self.waterfall_marker.setValue(self.freq.value())
        if self.worker and self.worker.is_alive():
            if self.scan_toggle.isChecked():
                self.scan_toggle.blockSignals(True)
                self.scan_toggle.setChecked(False)
                self.scan_toggle.blockSignals(False)
            self.worker.command('frequency', self.get_freq())

    def refresh_vfo_info(self, *_):
        if hasattr(self, 'vfo_info') and hasattr(self, 'mode'):
            rate_text = self.rate.currentText() if hasattr(self, 'rate') and self.rate.count() else 'SDR gereed'
            self.vfo_info.setText(f'VFO {self.vfos.active} · {self.mode.currentText()} · {rate_text} · STEP {self.step_combo.currentText()}')

    def mode_changed(self, value):
        if self._vfo_loading:
            return
        self.vfos.current().mode = value
        bw = DEFAULT_BW[value]
        self._set_bandwidth_limits(value)
        self.bandwidth_spin.setValue(bw)
        self.vfos.current().bandwidth_hz = bw
        self._sync_passband()
        self._update_vfo_labels()
        self.refresh_vfo_info()
        if self.worker and self.worker.is_alive():
            self.worker.command('mode', value)
            self.worker.command('bandwidth', bw)
            if self.rds_toggle.isChecked():
                self.worker.command('rds',self._redsea_executable() if value=='WFM' else None)

    def sql_changed(self, value):
        if not self._vfo_loading:
            self.vfos.current().squelch_dbfs = value
        self.sql_label.setText(f'{value} dBFS')
        if self.worker and self.worker.is_alive():
            self.worker.command('squelch', value)

    def volume_changed(self, value):
        self.vol_label.setText(f'{value}%')
        if self.worker and self.worker.is_alive():
            self.worker.command('volume', value / 100)

    def gain_changed(self, *_):
        self.gain.setEnabled(not self.gain_auto.isChecked())
        if self.worker and self.worker.is_alive():
            self.worker.command('gain', self.get_gain())

    def start_receiver(self):
        if self.worker and self.worker.is_alive():
            return
        if (self.decoder and self.decoder.state() != QtCore.QProcess.NotRunning) or (self.digital and self.digital.is_alive()):
            self.on_status('Stop eerst de digitale decoder.')
            return
        self.water.fill(-110)
        self.error_status = None
        dual_channels = None
        tuned_center = self.get_freq()
        if self.stereo_toggle.isChecked():
            if self.get_rate() >= 5_000_000:
                self.on_status('Stereo A/B vraagt veel DSP. Kies eerst 2,4 of 2,5 MSPS in het SDR-tabblad.')
                return
            av, bv = self.vfos.vfos['A'], self.vfos.vfos['B']
            dual_channels = [dict(frequency_hz=v.frequency_hz, mode=v.mode,
                                  bandwidth_hz=v.bandwidth_hz, squelch_dbfs=v.squelch_dbfs,
                                  passband_shift_hz=v.passband_shift_hz) for v in (av,bv)]
            try:
                tuned_center = center_and_validate(VFOChannel(**dual_channels[0]),
                                                  VFOChannel(**dual_channels[1]),self.get_rate())
            except ValueError as exc:
                self.on_status('Stereo A/B: ' + str(exc))
                return
        self._stereo_started = bool(dual_channels)
        self.worker = ReceiverWorker(self.source.currentText(), tuned_center, self.get_rate(),
                                     self.mode.currentText(), self.sql.value(), self.vol.value()/100,
                                     self.get_gain(), self.bus.frame.emit, self.bus.status.emit, self.bus.ended.emit,
                                     device_id=decode_device_id(self.device_list.currentData()),
                                     tune_callback=self.bus.tune_result.emit,
                                     stereo_vfos=dual_channels, rds_callback=self.bus.rds_result.emit)
        self.source.setEnabled(False)
        self.device_list.setEnabled(False)
        self.search_btn.setEnabled(False)
        self.rate.setEnabled(False)
        self.scan_toggle.setEnabled(not self._stereo_started)
        for control in (self.stereo_toggle,self.vfo_a_btn,self.vfo_b_btn,self.vfo_swap_btn,
                        self.vfo_copy_btn,self.freq,self.mode,self.bandwidth_spin,
                        self.pbt_shift,self.tune_up_btn,self.tune_down_btn,self.step_combo):
            if self._stereo_started:control.setEnabled(False)
        if self._stereo_started:
            for control in (self.audio_agc,self.notch_enabled,self.notch_freq,self.noise_reduction,
                            *self.eq_controls,self.eq_restore,self.scan_toggle):
                control.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.capture_btn.setEnabled(True)
        self.receiver_status.setText('RX actief  ·  stream starten...')
        if self._stereo_started:
            # Initialize both DSP channels before the worker starts. Runtime
            # filter changes are locked during dual operation, preventing
            # competing retune/DSP-reset commands.
            self.worker.agc = self.audio_agc.isChecked()
            self.worker.notch_hz = self.notch_freq.value() if self.notch_enabled.isChecked() else 0
            self.worker.noise_reduction = self.noise_reduction.isChecked()
            self.worker.eq_db = tuple(x.value() for x in self.eq_controls)
        else:
            self.worker.command('bandwidth', self.get_bandwidth())
            self.worker.command('agc', self.audio_agc.isChecked())
            self.worker.command('notch', self.notch_freq.value() if self.notch_enabled.isChecked() else 0)
            self.worker.command('noise_reduction', self.noise_reduction.isChecked())
            self.worker.command('passband_shift', self.pbt_shift.value())
            self.worker.command('equalizer', tuple(x.value() for x in self.eq_controls))
        self.worker.command('fft_size', int(self.fft_combo.currentText()))
        if self.rds_toggle.isChecked() and not self._stereo_started and self.mode.currentText() == 'WFM':
            executable = self._redsea_executable()
            if executable:
                self.worker.command('rds', executable)
            else:
                self.on_status('RDS: redsea.exe ontbreekt. Installeer de Windows-versie en selecteer deze in het SDR-tabblad.')
        if self._pending_iq_replay:
            self.worker.iq_replay_file = self._pending_iq_replay
            self._pending_iq_replay = None
        self.iq_replay_btn.setEnabled(False)
        self.iq_record_btn.setEnabled(self.worker.iq_replay_file is None)
        if self.worker.iq_replay_file:
            self.scan_toggle.setEnabled(False)
        self.worker.start()

    def stop_receiver(self):
        if self.worker:
            self.worker.stop()
            self.stop_btn.setEnabled(False)
            self.on_status('Ontvanger wordt afgesloten...')

    def on_worker_ended(self):
        self.receiver_status.setText('Stand-by  ·  geen IQ-stream')
        self.signal_meter.setValue(0)
        self.source.setEnabled(True)
        self.device_list.setEnabled(True)
        self.search_btn.setEnabled(True)
        self.rate.setEnabled(True)
        self.scan_toggle.blockSignals(True)
        self.scan_toggle.setChecked(False)
        self.scan_toggle.blockSignals(False)
        self.scan_toggle.setEnabled(False)
        for control in (self.stereo_toggle,self.vfo_a_btn,self.vfo_b_btn,self.vfo_swap_btn,
                        self.vfo_copy_btn,self.freq,self.mode,self.bandwidth_spin,
                        self.pbt_shift,self.tune_up_btn,self.tune_down_btn,self.step_combo):
            control.setEnabled(True)
        self._stereo_started = False
        for control in (self.audio_agc,self.notch_enabled,self.notch_freq,self.noise_reduction,
                        *self.eq_controls,self.eq_restore):
            control.setEnabled(True)
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.capture_btn.blockSignals(True)
        self.capture_btn.setChecked(False)
        self.capture_btn.blockSignals(False)
        self.capture_btn.setEnabled(False)
        self.iq_record_btn.blockSignals(True)
        self.iq_record_btn.setChecked(False)
        self.iq_record_btn.blockSignals(False)
        self.iq_record_btn.setEnabled(False)
        self.iq_record_btn.setText('● IQ-opname starten')
        self.iq_replay_btn.setEnabled(True)
        if self.error_status:
            self._full_status_text = self.error_status
            self._refresh_status_bar()
        else:
            self.on_status('Ontvanger gestopt.')
        self.worker = None
        if self.pending_decoder:
            self.pending_decoder = False
            self.launch_decoder()

    def on_frame(self, spectrum, frequency, rate, level):
        n = len(spectrum)
        if n != self.water.shape[1]:
            self.water = np.full((140, n), -110.0, dtype=np.float32)
        freqs = (frequency + np.linspace(-rate/2, rate/2, n, endpoint=False)) / 1e6
        self.curve.setData(freqs, spectrum)
        self._consume_auto_frame(spectrum, rate, frequency)
        if self._last_plot_rate != rate or self._last_plot_center != frequency:
            self._last_plot_center, self._last_plot_rate = frequency, rate
            self.water.fill(-110)
            self._set_plot_range(frequency, rate)
        self._water_count += 1
        interval = int(self.wf_speed.currentText().replace('×', ''))
        if self._water_count % interval == 0:
            self.water[1:] = self.water[:-1].copy()
            self.water[0] = spectrum
            bottom = self.wf_floor.value()
            top = max(bottom + 10, self.wf_ceiling.value())
            self.wf_image.setImage(self.water, autoLevels=False, levels=(bottom, top))
        self.wf_image.setRect(QtCore.QRectF(float(freqs[0]), 0, rate / 1e6, len(self.water)))
        if self.scan_toggle.isChecked() and abs(self.freq.value()*1e6 - frequency) > 0.5:
            self.freq.blockSignals(True)
            self.freq.setValue(frequency / 1e6)
            self.freq.blockSignals(False)
            self._step_anchor_hz = self.get_freq()
            self._step_count = 0
            if self.worker and self.mode.currentText() != self.worker.mode:
                self.mode.blockSignals(True)
                self.mode.setCurrentText(self.worker.mode)
                self.mode.blockSignals(False)
                self.vfos.current().mode = self.worker.mode
                self._set_bandwidth_limits(self.worker.mode)
                self.bandwidth_spin.blockSignals(True)
                self.bandwidth_spin.setValue(self.worker.bandwidth_hz)
                self.bandwidth_spin.blockSignals(False)
            self.vfos.current().frequency_hz = frequency
            self._update_vfo_labels()
            self._sync_passband()
            self.tune_marker.setValue(self.freq.value())
            self.waterfall_marker.setValue(self.freq.value())
        peak = self.peak_meter.update(level)
        self.meter.setText(f'RF: {level:+.1f} dBFS')
        smeter = calibrated_s_reading(level, self.dbm_reference.value() if self.s_calibrated.isChecked() else None)
        self.peak_label.setText(f'Piek: {peak:+.1f} dBFS  ·  {smeter or "S-meter: niet gekalibreerd"}')
        self.signal_meter.setValue(max(0, min(100, round(level + 110))))
        self.receiver_status.setText(f'RX actief  ·  {rate / 1e6:g} MSPS')
        self.vfo_info.setText(('DUAL RX  ·  VFO A links / VFO B rechts' if self._stereo_started else
                               f'VFO {self.vfos.active} · {self.mode.currentText()} · {rate / 1e6:g} MSPS · STEP {self.step_combo.currentText()}'))
        if time.monotonic()-self._hint_at > 2.0:
            self._hint_at = time.monotonic()
            hint = signal_hint(spectrum,rate,frequency)
            self.rf_hint.setText('RF indicatie: ' + hint.label + '\n' + hint.reason)

    def spectrum_clicked(self, ev):
        if ev.button() != QtCore.Qt.LeftButton:
            return
        vb = self.spectrum.getViewBox()
        point = vb.mapSceneToView(ev.scenePos())
        mhz = point.x()
        if 0.01 <= mhz <= 2000:
            self.freq.setValue(mhz)

    def _redsea_executable(self):
        from shutil import which
        entry = self.redsea_path.text().strip().strip('"')
        if entry and (Path(entry).is_file() or which(entry)):
            return entry
        return self.find_local_decoder('redsea') or (which('redsea') or '')

    def browse_redsea(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self,'Kies redsea.exe',
                  str(Path.home() / 'Downloads'),'Uitvoerbare bestanden (*.exe);;Alle bestanden (*)')
        if path:
            self.redsea_path.setText(path)
            self.settings.setValue('redsea_path',path)

    def toggle_rds(self, enabled):
        self.rds_display.setText('PS: —   ·   PI: —\nRadiotekst: —')
        if self.worker and self.worker.is_alive():
            if enabled and (self.mode.currentText() != 'WFM' or self._stereo_started):
                self.on_status('RDS vereist WFM en enkele VFO.')
                self.rds_toggle.blockSignals(True)
                self.rds_toggle.setChecked(False)
                self.rds_toggle.blockSignals(False)
                return
            exe = self._redsea_executable() if enabled else None
            if enabled and not exe:
                self.on_status('RDS: selecteer eerst redsea.exe (externe decoder, niet inbegrepen).')
                self.rds_toggle.blockSignals(True)
                self.rds_toggle.setChecked(False)
                self.rds_toggle.blockSignals(False)
                return
            self.worker.command('rds',exe)

    def on_rds_result(self, event):
        ps=event.get('ps') or '—'
        pi=event.get('pi') or '—'
        pty=event.get('pty') or ''
        radiotext=event.get('text') or '—'
        self.rds_display.setText(f'PS: {ps}   ·   PI: {pi}   {pty}\nRadiotekst: {radiotext}')

    def toggle_rf_monitor(self, enabled):
        if enabled:
            self.rf_monitor.reset()
            self._auto_frame_at = 0.0
            self.auto_info.setText('AUTO monitor actief · wacht op stabiele RF-kandidaten (geen protocolherkenning).')
        else:
            self.auto_info.setText('AUTO monitor uit · bewaarde kandidaatlijst blijft beschikbaar.')

    def update_auto_sensitivity(self, value):
        self.rf_monitor.threshold_db = float(value)
        self.rf_monitor.reset()

    def clear_auto_candidates(self):
        self.auto_candidates.clear()
        self._auto_counters['rf'] = 0
        self.rf_monitor.reset()
        self.auto_info.setText('RF-lijst gewist. RF detectie ≠ bevestigde digitale mode.')

    def _selected_auto_frequency(self):
        item = self.auto_candidates.currentItem()
        if item is None:
            self.on_status('Selecteer eerst een gevonden RF-kandidaat.')
            return None
        try:
            return int(item.data(0, QtCore.Qt.ItemDataRole.UserRole))
        except (TypeError, ValueError):
            return None

    def tune_auto_candidate(self):
        frequency = self._selected_auto_frequency()
        if frequency is None:
            return
        if self.digital and self.digital.is_alive():
            self.on_status('Stop de decoder voordat je een RF-kandidaat afstemt.')
            return
        if self._stereo_started:
            self.on_status('Stop eerst Dual RX; tijdens dubbele ontvangst is afstemmen uitgeschakeld.')
            return
        if self.scan_toggle.isChecked():
            self.scan_toggle.setChecked(False)
        self.freq.setValue(frequency / 1e6)
        self.on_status(f'RF-kandidaat afgestemd: {frequency/1e6:.6f} MHz · protocol onbekend')

    def verify_auto_candidate(self):
        if self._selected_auto_frequency() is None:
            return
        if self._stereo_started:
            self.on_status('Stop Dual RX voordat je een decoder gebruikt.')
            return
        self.tune_auto_candidate()
        self.start_digital_auto()

    def start_auto_scan(self):
        if not (self.worker and self.worker.is_alive()):
            self.on_status('Start eerst de gewone SDR-ontvanger.')
            return
        if self._stereo_started:
            self.on_status('Scan is niet beschikbaar tijdens Dual RX.')
            return
        self.auto_toggle.setChecked(True)
        # Two stable measurements require >= 1.8s on a channel.
        # Leave extra margin for GUI refresh and retune latency.
        if self.scan_dwell.value() < 2500:
            self.scan_dwell.setValue(2500)
        if self.scan_toggle.isChecked():
            self.scan_toggle.setChecked(False)
        # Reuse the existing bounded frequency-range/memory scanner, avoiding
        # a second thread competing for the hardware receiver.
        if not self.scan_toggle.isChecked():
            self.scan_toggle.setChecked(True)
        if self.scan_toggle.isChecked():
            self.on_status('Scanner en RF-monitor actief; dwell minimaal 2500 ms voor stabiele detectie.')

    def export_auto_candidates(self):
        if self.auto_candidates.topLevelItemCount() == 0:
            self.on_status('Geen RF-kandidaten om te exporteren.')
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Exporteer RF-kandidaten',
                                                         'digital-auto-rf-kandidaten.csv', 'CSV (*.csv)')
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['Tijd', 'Frequentie Hz', 'SNR-indicatie dB', 'Breedte Hz', 'Status'])
                for i in range(self.auto_candidates.topLevelItemCount()):
                    item = self.auto_candidates.topLevelItem(i)
                    writer.writerow([item.toolTip(0), item.data(0, QtCore.Qt.ItemDataRole.UserRole),
                                     item.text(1),item.text(2),item.text(3)])
            self.on_status('RF-kandidaten geëxporteerd: ' + path)
        except OSError as exc:
            self.on_status('FOUT: RF-export: ' + str(exc))

    def _consume_auto_frame(self, spectrum, rate, center):
        if not self.auto_toggle.isChecked():
            return
        now = time.monotonic()
        if now - self._auto_frame_at < 0.9:
            return
        self._auto_frame_at = now
        for item in self.rf_monitor.update(spectrum, int(rate), int(center), now=now):
            line = QtWidgets.QTreeWidgetItem([
                f'{item.frequency_hz/1e6:.6f}', f'+{item.over_noise_db:.1f} dB',
                f'{item.width_hz/1000:.1f} kHz', 'Onbekend · RF'])
            line.setData(0, QtCore.Qt.ItemDataRole.UserRole, int(item.frequency_hz))
            line.setToolTip(0, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            line.setToolTip(3, 'Alleen FFT-energie gedetecteerd; geen DMR/P25/NXDN-bevestiging')
            self.auto_candidates.addTopLevelItem(line)
            if self.auto_candidates.topLevelItemCount() > 150:
                self.auto_candidates.takeTopLevelItem(0)
            self._auto_counters['rf'] += 1
        self.auto_info.setText(f"RF-waarnemingen: {self._auto_counters['rf']} · "
                               f"decodergebeurtenissen: {self._auto_counters['protocol']} · "
                               'RF alleen bewijst geen digitaal protocol')

    def start_digital_auto(self):
        auto_index = next((i for i,d in enumerate(DECODERS) if 'DSD-neo · Digital Auto' == d.label),None)
        if auto_index is None:
            self.on_status('Geen DSD-neo AUTO-profiel gevonden.')
            return
        self.decoder_combo.setCurrentIndex(auto_index)
        if not (Path(self.exec_name.text()).is_file() or shutil.which(self.exec_name.text())):
            self.on_status('Digitale AUTO-herkenning vereist de externe Windows DSD-neo runtime in decoders/bin.')
            return
        self.on_status('Start digitale AUTO via DSD-neo (niet te verwarren met RF-vormherkenning).')
        self.start_decoder()

    def open_drivers_folder(self):
        folder = Path(__file__).resolve().parent.parent / 'drivers'
        folder.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(folder)))
        self.on_status('Airspy DLL-map geopend. Zet de x64 libairspy.dll en zijn afhankelijkheden hier.')

    def _refresh_status_bar(self):
        value = getattr(self, '_full_status_text', '')
        if not hasattr(self, 'status_bar'):
            return
        # Pixel-based elision, not truncation of the full diagnostic in the log.
        available = max(100, self.status_bar.width() - 12)
        rendered = self.status_bar.fontMetrics().elidedText(
            value.replace('\r', ' ').replace('\n', ' '),
            QtCore.Qt.TextElideMode.ElideRight, available)
        self.status_bar.setText(rendered)
        self.status_bar.setToolTip(value)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_status_bar()

    def on_status(self, value):
        if value.startswith('FOUT:'):
            self.error_status = value
        if 'libairspy.dll' in value or 'airspy.dll' in value:
            self._full_status_text = ('Airspy R2: DLL ontbreekt of kan niet laden. '
                                      'Open de drivers-map en lees het log.')
        else:
            self._full_status_text = value
        self._refresh_status_bar()
        self.log.appendPlainText(value)

    def memory_group_changed(self, *_):
        group = self.mem_group.currentText()
        if hasattr(self, 'scan_group') and self.scan_group.currentText() != group:
            self.scan_group.blockSignals(True)
            self.scan_group.setCurrentText(group)
            self.scan_group.blockSignals(False)
        self.refresh_memories()
        if hasattr(self, 'scan_toggle') and self.scan_toggle.isChecked():
            self.scanner_changed(True)

    def refresh_memories(self, *_):
        selected = self.mem_group.currentText()
        self.memory_group_names = merge_groups(self.memory_group_names, self.memories)
        options = [ALL_GROUPS, *self.memory_group_names]
        self.mem_group.blockSignals(True)
        self.mem_group.clear()
        self.mem_group.addItems(options)
        self.mem_group.setCurrentText(selected if selected in options else ALL_GROUPS)
        self.mem_group.blockSignals(False)
        # Keep the scanner's group selector in sync with the Geheugens tab.
        self.scan_group.blockSignals(True)
        self.scan_group.clear()
        self.scan_group.addItems(options)
        self.scan_group.setCurrentText(self.mem_group.currentText())
        self.scan_group.blockSignals(False)
        self._visible_memories = sorted(group_members(self.memories, self.mem_group.currentText()),
                                        key=lambda row: (memory_group(row).casefold(), row['frequency'], row['name'].casefold()))
        self.memlist.clear()
        if hasattr(self, 'scan_toggle') and self.worker and self.worker.is_alive():
            self.scan_toggle.setEnabled(True)
        self.update_scan_summary()
        for mem in self._visible_memories:
            shortcut = f" · F{mem['shortcut']}" if mem.get('shortcut') else ''
            star = '★ ' if mem.get('favorite') else ''
            group_label = f"[{memory_group(mem)}] " if self.mem_group.currentText() == ALL_GROUPS else ''
            scan_label = '' if mem.get('scan_enabled', True) is not False else ' · SCAN UIT'
            item = QtWidgets.QListWidgetItem(f"{group_label}{star}{mem['name']} · {mem['frequency']/1e6:.6f} MHz · {mem['mode']}{shortcut}{scan_label}")
            item.setToolTip(str(mem.get('comment', '')) + ('\nNiet meegenomen in groepsscan' if scan_label else ''))
            self.memlist.addItem(item)

    def create_memory_group(self):
        name, ok = QtWidgets.QInputDialog.getText(self, 'Nieuwe groep', 'Naam van nieuwe groep (bijv. Beek):')
        if not ok:
            return
        try:
            proposed = create_group(self.memory_group_names, name)
            self.memory_group_names = save_group_names(proposed)
        except (OSError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(self, 'Geheugengroepen', str(exc))
            return
        self.refresh_memories()
        self.mem_group.setCurrentText(normalize_group(name))

    def rename_memory_group(self):
        old = self.mem_group.currentText()
        if old in (ALL_GROUPS, DEFAULT_GROUP):
            QtWidgets.QMessageBox.information(self, 'Geheugengroepen', 'Selecteer een eigen groep om te hernoemen.')
            return
        name, ok = QtWidgets.QInputDialog.getText(self, 'Groep hernoemen', 'Nieuwe naam:', text=old)
        if not ok:
            return
        try:
            new_groups, new_memories = rename_group(self.memory_group_names, self.memories, old, name)
            # Save channel data before updating catalogue: if interrupted, old group remains discoverable.
            save_memories(new_memories)
            save_group_names(new_groups)
            # Stop the old scan before the group selectors refresh; otherwise
            # the temporary fallback to Alle groepen could widen the scan.
            was_scanning = self.scan_toggle.isChecked()
            if was_scanning:
                self.scan_toggle.setChecked(False)
            self.memories, self.memory_group_names = new_memories, new_groups
        except (OSError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(self, 'Geheugengroepen', str(exc))
            return
        self.refresh_memories()
        self.mem_group.setCurrentText(normalize_group(name))
        if was_scanning:
            self.on_status('Groep hernoemd; de scanner is gestopt. Start opnieuw met de gekozen groep.')

    def delete_memory_group(self):
        old = self.mem_group.currentText()
        if old in (ALL_GROUPS, DEFAULT_GROUP):
            QtWidgets.QMessageBox.information(self, 'Geheugengroepen', 'Selecteer een eigen groep om te verwijderen.')
            return
        number = len(group_members(self.memories, old))
        message = (f'Groep "{old}" verwijderen?\n\nDe {number} bijbehorende kanalen '
                   'worden bewaard in de groep Algemeen.')
        if QtWidgets.QMessageBox.question(self, 'Groep verwijderen', message) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        was_scanning = self.scan_toggle.isChecked()
        if was_scanning:
            self.scan_toggle.setChecked(False)
        try:
            new_groups, new_memories = delete_group(self.memory_group_names, self.memories, old)
            save_memories(new_memories)
            save_group_names(new_groups)
            self.memories, self.memory_group_names = new_memories, new_groups
        except (OSError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(self, 'Geheugengroepen', str(exc))
            return
        self.refresh_memories()
        if self.scan_toggle.isChecked():
            # Do not silently expand scanning to all groups on group deletion.
            self.scan_toggle.setChecked(False)
            self.on_status('Groep verwijderd; geheugen-scan gestopt. Kies opnieuw een groep.')

    def _edit_memory(self, previous=None):
        dialog = MemoryEditDialog(self, self.memory_group_names, previous)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        item = dialog.result_memory(previous)
        slot = item['shortcut']
        if slot and any(m is not previous and int(m.get('shortcut', 0) or 0) == slot for m in self.memories):
            QtWidgets.QMessageBox.warning(self, 'Sneltoets bezet', f'F{slot} is al aan een ander kanaal toegewezen.')
            return
        try:
            new_groups = self.memory_group_names
            existing = next((g for g in new_groups if g.casefold() == item['group'].casefold()), None)
            if existing is None:
                new_groups = create_group(new_groups, item['group'])
            else:
                item['group'] = existing
            updated = [item if m is previous else m for m in self.memories] if previous is not None else [*self.memories, item]
            save_memories(updated)
            save_group_names(new_groups)
        except (OSError, ValueError) as exc:
            QtWidgets.QMessageBox.warning(self, 'Opslaan mislukt', str(exc))
            return
        self.memories, self.memory_group_names = updated, new_groups
        self.refresh_memories()
        self.mem_group.setCurrentText(item['group'])
        if self.scan_toggle.isChecked():
            self.scanner_changed(True)

    def add_memory(self):
        self._edit_memory()

    def edit_memory(self):
        index = self.memlist.currentRow()
        if index < 0:
            QtWidgets.QMessageBox.information(self, 'Geheugen', 'Selecteer eerst een opgeslagen kanaal.')
            return
        self._edit_memory(self._visible_memories[index])

    def goto_memory(self):
        row = self.memlist.currentRow()
        if row < 0:
            return
        mem = self._visible_memories[row]
        self.mode.setCurrentText(mem['mode'])
        self.freq.setValue(mem['frequency']/1e6)

    def delete_memory(self):
        row = self.memlist.currentRow()
        if row < 0:
            return
        mem = self._visible_memories[row]
        self.memories.remove(mem)
        save_memories(self.memories)
        self.refresh_memories()
        if self.scan_toggle.isChecked():
            self.scanner_changed(True)

    def goto_shortcut(self, number):
        mem = shortcut_memory(self.memories, number)
        if mem:
            self.mode.setCurrentText(mem['mode'])
            self.freq.setValue(mem['frequency'] / 1e6)
            self.on_status(f'F{number}: {mem["name"]}')

    def toggle_iq_recording(self, active):
        if not self.worker or not self.worker.is_alive():
            return
        if active:
            if self._last_plot_rate is not None:
                rate = self._last_plot_rate
            else:
                rate = self.get_rate()
            if rate >= 5_000_000:
                answer = QtWidgets.QMessageBox.question(self, 'IQ-opname bij hoge sample-rate',
                    '10 MSPS gebruikt circa 80 MB/s opslagruimte. Doorgaan?')
                if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                    self.iq_record_btn.blockSignals(True)
                    self.iq_record_btn.setChecked(False)
                    self.iq_record_btn.blockSignals(False)
                    return
            root = Path.home() / 'SDRStudio-RX' / 'iq_recordings'
            root.mkdir(parents=True, exist_ok=True)
            name = f'{datetime.now():%Y%m%d-%H%M%S-%f}_{self.get_freq()}Hz.cf32'
            self.worker.command('iq_record', str(root / name))
            self.iq_record_btn.setText('■ Stop IQ-opname')
        else:
            self.worker.command('iq_record', None)
            self.iq_record_btn.setText('● IQ-opname starten')

    def open_iq_replay(self):
        if self.worker and self.worker.is_alive():
            self.on_status('Stop eerst de ontvanger voordat je IQ afspeelt.')
            return
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Open CF32LE IQ-bestand',
                    str(Path.home() / 'SDRStudio-RX' / 'iq_recordings'), 'CF32LE IQ (*.cf32)')
        if not filename:
            return
        try:
            import json
            info = json.loads(metadata_file(filename).read_text(encoding='utf-8'))
            if info.get('format') != 'CF32LE':
                raise ValueError('Ongeldig IQ-formaat')
            center = int(info['center_hz'])
            if not self.freq.minimum()*1e6 <= center <= self.freq.maximum()*1e6:
                raise ValueError('Opnamefrequentie buiten bereik van invoerveld')
            self.freq.setValue(center/1e6)
            self._pending_iq_replay = filename
            self.on_status(f'IQ-replay geselecteerd: {Path(filename).name}; start ontvanger met ONTVANGEN')
            self.start_receiver()
        except (OSError, ValueError, KeyError) as exc:
            self.on_status(f'FOUT: IQ-bestand: {exc}')

    def scanner_changed(self, checked):
        if self._stereo_started:
            self.on_status('Scanner is niet beschikbaar tijdens dubbele stereo-ontvangst.')
            return
        if not (self.worker and self.worker.is_alive()):
            return
        if not checked:
            self.worker.command('scan', None)
            return
        try:
            config = self.scan_configuration()
        except ValueError as exc:
            self.on_status('FOUT: Scanner: ' + str(exc))
            self.scan_toggle.blockSignals(True)
            self.scan_toggle.setChecked(False)
            self.scan_toggle.blockSignals(False)
            return
        self.worker.command('scan', config)

    def toggle_recording(self, is_recording):
        if not self.worker:
            return
        if is_recording:
            from datetime import datetime
            root = Path.home() / 'SDRStudio-RX' / 'recordings'
            root.mkdir(parents=True, exist_ok=True)
            file = root / f'{datetime.now():%Y%m%d-%H%M%S}_{self.get_freq()}Hz.wav'
            self.worker.command('record', str(file))
            self.capture_btn.setText('■ Stop WAV')
        else:
            self.worker.command('record', None)
            self.capture_btn.setText('● WAV opname')

    def decoder_changed(self, *_):
        if not hasattr(self, 'decoder_combo') or not hasattr(self, 'source'):
            return
        choice = DECODERS[self.decoder_combo.currentIndex()]
        device = self.source.currentText()
        executable, arguments = decoder_template(choice, self.get_freq(), device)
        # Find binaries shipped by the user in decoders/bin, without bundling
        # third-party code or guessing arbitrary installation locations.
        local = self.find_local_decoder(executable)
        self.exec_name.setText(local or executable)
        self.decoder_args.setText(arguments)
        self.decoder_info.setText(decoder_description(choice, device))
        self.decoder_project_btn.setEnabled(bool(choice.link))
        self.preset_btn.setEnabled(bool(choice.preset_hz))
        connection_type = ('Live IQ/audio-brug: ' + choice.stream.upper() if choice.stream else
                           'Eigen SDR van decoder' if choice.approach == 'external-rtl' else
                           'Virtuele audio/externe applicatie' if choice.approach == 'audio/iq' else
                           'Handmatig extern proces')
        self.decoder_availability.setText(
            connection_type +
            (' | Decoder gevonden' if local or shutil.which(executable or 'NONEXISTENT') else
             ' | Installeer de externe decoder')
        )

    @staticmethod
    def find_local_decoder(name: str) -> str:
        """Find tools in portable per-decoder folders, preserving their DLLs."""
        from .decoder_locations import locate_decoder
        return locate_decoder(name)

    def open_decoder_project(self):
        profile = DECODERS[self.decoder_combo.currentIndex()]
        if profile.link:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(profile.link))

    def browse_decoder_exe(self):
        path, _filter = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Selecteer decoderprogramma', str(Path.home() / 'Downloads'),
            'Executables (*.exe);;Alle bestanden (*)')
        if path:
            self.exec_name.setText(path)
            self.decoder_availability.setText('Handmatig gekozen: ' + Path(path).name)

    def on_decoder_line(self, line):
        self.log.appendPlainText('[DIG] ' + line[:400])

    def tune_decoder_preset(self):
        profile = DECODERS[self.decoder_combo.currentIndex()]
        if not profile.preset_hz:
            return
        if self.worker and self.worker.is_alive() or self.digital and self.digital.is_alive():
            self.on_status('Stop eerst de ontvangst om het decoderpreset te kiezen.')
            return
        self.freq.setValue(profile.preset_hz / 1_000_000)
        if profile.stream in ('audio16', 'voice16'):
            self.mode.setCurrentText('NFM')
        self.decoder_changed()

    def start_decoder(self):
        if self.digital and self.digital.is_alive():
            return
        if self.decoder and self.decoder.state() != QtCore.QProcess.NotRunning:
            return
        profile = DECODERS[self.decoder_combo.currentIndex()]
        if self.worker and self.worker.is_alive() and profile.approach != 'audio/iq':
            # A stream decoder or an externally controlled SDR needs exclusive
            # USB ownership. A virtual-audio application needs RX to keep playing.
            self.pending_decoder = True
            self.stop_receiver()
        else:
            self.launch_decoder()

    def _disable_for_decoder(self, active):
        for control in (self.source, self.device_list, self.search_btn, self.rate,
                        self.start_btn, self.freq, self.step_combo, self.tune_up_btn, self.tune_down_btn,
                        self.gain, self.gain_auto, self.mode, self.bandwidth_spin,
                        self.vfo_a_btn, self.vfo_b_btn, self.vfo_swap_btn, self.vfo_copy_btn,
                        self.scan_toggle):
            control.setEnabled(not active)
        self.decoder_combo.setEnabled(not active)
        self.exec_name.setEnabled(not active)
        self.decoder_args.setEnabled(not active)
        self.preset_btn.setEnabled(not active and bool(DECODERS[self.decoder_combo.currentIndex()].preset_hz))
        self.decoder_btn.setEnabled(not active)
        self.decoder_stop.setEnabled(active)

    def launch_stream_decoder(self, profile):
        executable = self.exec_name.text().strip()
        if not executable or not (Path(executable).is_file() or shutil.which(executable)):
            self.on_status('FOUT: Installeer eerst de decoder in decoders/bin of geef het pad naar de .exe op.')
            return
        try:
            args = shlex.split(self.decoder_args.text(), posix=True)
            # stream_command validates the selected input protocol.
            stream_command(profile, self.get_freq(), self.source.currentText())
        except (ValueError, OSError) as exc:
            self.on_status(f'FOUT: Decoderinstellingen ongeldig: {exc}')
            return
        self.digital = DigitalDecoderWorker(
            profile=profile, exe=executable, frequency=self.get_freq(),
            sample_rate=self.get_rate(), kind=self.source.currentText(),
            gain=self.get_gain(), device_id=decode_device_id(self.device_list.currentData()),
            frame_callback=self.bus.frame.emit, status_callback=self.bus.status.emit,
            event_callback=self.bus.digital_event.emit,
            ended_callback=self.bus.digital_ended.emit, line_callback=self.bus.digital_line.emit,
            args_override=args)
        self._disable_for_decoder(True)
        self.stereo_toggle.setEnabled(False)
        self.receiver_status.setText('DIGITAAL  ·  IQ-brug bezig...')
        self.digital.start()

    def on_decoder_event(self, event: DecoderEvent):
        self._auto_counters['protocol'] += 1
        entry = QtWidgets.QTreeWidgetItem([datetime.now().strftime('%H:%M:%S'),
                                          event.protocol + ' / ' + event.identifier, event.detail])
        entry.setToolTip(2, event.raw)
        self.event_table.addTopLevelItem(entry)
        if self.event_table.topLevelItemCount() > 250:
            self.event_table.takeTopLevelItem(0)
        self.event_table.scrollToBottom()
        self._event_count += 1
        self.event_counter.setText(f'{self._event_count} decoderberichten ontvangen (maximaal 250 zichtbaar)')
        self.filter_decoder_events(self.event_filter.text())

    def export_decoder_events(self):
        if not self.event_table.topLevelItemCount():
            self.on_status('Geen decoderberichten om te exporteren.')
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Exporteer decoderberichten',
                                                         'decoder-berichten.csv', 'CSV (*.csv)')
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as file:
                writer = csv.writer(file, delimiter=';')
                writer.writerow(['Tijd', 'Protocol', 'Bericht'])
                for i in range(self.event_table.topLevelItemCount()):
                    entry = self.event_table.topLevelItem(i)
                    writer.writerow([entry.text(j) for j in range(3)])
            self.on_status('Decoderberichten geëxporteerd: ' + path)
        except OSError as exc:
            self.on_status('FOUT: CSV export mislukt: ' + str(exc))

    def on_digital_ended(self):
        self.digital = None
        self._disable_for_decoder(False)
        self.stereo_toggle.setEnabled(True)
        self.receiver_status.setText('Stand-by  ·  geen IQ-stream')
        self.on_status('Digitale IQ-bridge gestopt. Ontvanger weer vrij.')

    def launch_decoder(self):
        profile = DECODERS[self.decoder_combo.currentIndex()]
        if profile.stream:
            self.launch_stream_decoder(profile)
            return
        exe = self.exec_name.text().strip()
        if not exe:
            self.on_status('Geef de executable van de externe decoder op.')
            return
        # Optional local path (for example C:/tools/rtl_433.exe) or PATH binary.
        if not (Path(exe).is_file() or shutil.which(exe)):
            self.on_status(f'Decoder niet gevonden: {exe}. Download en configureer eerst de externe tool.')
            return
        self.decoder = QtCore.QProcess(self)
        self._decoder_output_pending = ''
        self._active_external_decoder = profile.label
        self.decoder.setProcessChannelMode(QtCore.QProcess.MergedChannels)
        self.decoder.readyReadStandardOutput.connect(self.decoder_output)
        self.decoder.finished.connect(self.decoder_ended)
        self.decoder.errorOccurred.connect(self.decoder_error)
        try:
            args = shlex.split(self.decoder_args.text(), posix=True)
        except ValueError as exc:
            self.on_status(f'Ongeldige decoderargumenten: {exc}')
            return
        self.decoder.setProgram(exe)
        self.decoder.setArguments(args)
        self.decoder.start()
        self.decoder_btn.setEnabled(False)
        self.decoder_stop.setEnabled(True)
        if profile.approach != 'audio/iq':
            self.start_btn.setEnabled(False)
        self.on_status(f'Externe decoder gestart: {exe} {self.decoder_args.text()}')

    def decoder_error(self, error):
        self.on_status(f'Decoderfout: {self.decoder.errorString()}')
        self.decoder_btn.setEnabled(True)
        self.decoder_stop.setEnabled(False)
        self.start_btn.setEnabled(not (self.worker and self.worker.is_alive()))

    def decoder_output(self):
        # QProcess may deliver half a decoder line at a time. Only parse
        # complete newline-delimited messages into protocol events.
        msg = bytes(self.decoder.readAllStandardOutput()).decode('utf-8', errors='replace')
        self._decoder_output_pending = (getattr(self, '_decoder_output_pending', '') + msg)[-32768:]
        while '\n' in self._decoder_output_pending:
            line, self._decoder_output_pending = self._decoder_output_pending.split('\n', 1)
            line = line.strip()
            if line:
                self.log.appendPlainText(line[-5000:])
                event = parse_decoder_line(self._active_external_decoder, line)
                if event:
                    self.on_decoder_event(event)

    def stop_decoder(self):
        if self.pending_decoder:
            self.pending_decoder = False
        if self.digital and self.digital.is_alive():
            self.digital.stop()
            self.on_status("Digitale IQ-bridge wordt afgesloten...")
            return
        if self.decoder and self.decoder.state() != QtCore.QProcess.NotRunning:
            self.decoder.terminate()
            # QProcess.kill() only if exit fails; no blocking of UI.
            QtCore.QTimer.singleShot(2000, self.kill_decoder_if_needed)

    def kill_decoder_if_needed(self):
        if self.decoder and self.decoder.state() != QtCore.QProcess.NotRunning:
            self.decoder.kill()

    def decoder_ended(self, exit_code, status):
        if getattr(self, '_decoder_output_pending', '').strip():
            line = self._decoder_output_pending.strip()
            event = parse_decoder_line(self._active_external_decoder, line)
            if event:
                self.on_decoder_event(event)
        self._decoder_output_pending = ''
        self.decoder_btn.setEnabled(True)
        self.decoder_stop.setEnabled(False)
        self.start_btn.setEnabled(not (self.worker and self.worker.is_alive()))
        self.on_status(f'Externe decoder gestopt (exit {exit_code})')

    def closeEvent(self, event):
        if self.digital and self.digital.is_alive():
            self.digital.stop()
            self.digital.join(timeout=3.0)
            if self.digital.is_alive():
                event.ignore()
                self.on_status('Wacht tot de digitale ontvanger is afgesloten.')
                return
        if self.worker and self.worker.is_alive():
            self.worker.stop()
            # Allow the receiver thread to finish its current read and close USB.
            self.worker.join(timeout=3.0)
            if self.worker.is_alive():
                event.ignore()
                self.on_status('USB-ontvanger wordt nog afgesloten. Wacht even en sluit daarna opnieuw.')
                return
        if self.decoder and self.decoder.state() != QtCore.QProcess.NotRunning:
            self.decoder.kill()
            self.decoder.waitForFinished(1000)
        self._save_vfos()
        super().closeEvent(event)


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    window = Window()
    window.show()
    sys.exit(app.exec())
