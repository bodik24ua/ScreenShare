import sys
import os
import time
import threading
import concurrent.futures
from io import BytesIO

import qrcode
import requests
import mss
from PIL import Image
from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QGridLayout,
    QMessageBox,
    QHBoxLayout,
)
from PyQt5.QtCore import Qt, QSize, pyqtSignal, QTimer, QPoint, QUrl
from PyQt5.QtGui import (
    QPixmap,
    QImage,
    QShowEvent,
    QLinearGradient,
    QPalette,
    QColor,
    QMouseEvent,
    QDesktopServices,
)


class MonitorPreviewWidget(QWidget):
    monitor_selected = pyqtSignal(int)

    def __init__(self, monitor_index, monitor_geometry, parent=None):
        super().__init__(parent)
        self.monitor_index = monitor_index
        self.monitor_geometry = monitor_geometry
        self.setCursor(Qt.PointingHandCursor)
        self.layout = QGridLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.size_label = QLabel(
            f"{monitor_geometry['width']}x{monitor_geometry['height']}"
        )
        self.size_label.setStyleSheet(
            "color: lightgray; font-size: 10px; margin-bottom: -3px;"
        )
        self.size_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.size_label, 0, 0)

        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.preview_label)

        self.setStyleSheet("margin: 5px;")

    def mousePressEvent(self, event):
        self.monitor_selected.emit(self.monitor_index)

    def setPixmap(self, pixmap):
        self.preview_label.setPixmap(pixmap)

    def width(self):
        return self.preview_label.width()

    def height(self):
        return self.layout.sizeHint().height()


class ScreenshotAppGUI(QWidget):
    monitors_changed = pyqtSignal(list)

    PRIMARY_BUTTON_STYLE = """
        QPushButton {
            background-color: #002C3D;
            color: white;
            padding: 10px;
            border-radius: 5px;
        }
        QPushButton:hover {
            background-color: #154E66;
        }
    """
    ABOUT_DIALOG_STYLE = """
        QMessageBox {
            background-color: #2E2E2E;
        }
        QLabel {
            color: lightgray;
        }
        QPushButton {
            background-color: #444444;
            color: white;
            padding: 10px;
            border-radius: 5px;
        }
        QPushButton:hover {
            background-color: #555555;
        }
    """
    DEFAULT_STYLE = """
        QWidget {
            color: lightgray;
        }
        QLabel {
            color: lightgray;
        }
    """
    TIMER_DELAY = 3000
    WINDOW_ADJUST_DELAY = 1500
    PREVIEW_UPDATE_DELAY = 2000
    VERSION = "1.0.0"

    def __init__(
        self,
        command_queue,
        initial_monitors,
        code,
        initial_monitor_index=0,
        preview_update_interval=PREVIEW_UPDATE_DELAY,
        max_preview_width=200,
        max_concurrent_preview_updates=2,
    ):
        super().__init__()
        self.command_queue = command_queue
        self.monitors = list(initial_monitors)
        self._dragging = False
        self._offset = QPoint()
        self.code = code
        self.setWindowTitle("AirVerse Screen Share")
        self.setWindowOpacity(0.95)

        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, QColor("#000033"))
        gradient.setColorAt(1.0, QColor("#00151C"))
        palette = self.palette()
        palette.setBrush(QPalette.Background, gradient)
        self.setAutoFillBackground(True)
        self.setPalette(palette)

        self.setStyleSheet(self.DEFAULT_STYLE)

        self.selected_monitor_index = initial_monitor_index
        self.preview_update_interval = preview_update_interval
        self.max_preview_width = max_preview_width
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_concurrent_preview_updates
        )

        script_dir = os.path.dirname(os.path.abspath(__file__))
        image_path = os.path.join(script_dir, "AirVerseLogo.png")
        pixmap = QPixmap(image_path)
        scaled_pixmap = pixmap

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignRight)
        self.image_label.setPixmap(scaled_pixmap)

        self.title_label = QLabel("Pass Key")
        self.title_label.setStyleSheet("font-size: 14px;")
        self.title_label.setAlignment(Qt.AlignLeft)

        self.topic_label = QLabel(f"{self.code}")
        self.topic_label.setStyleSheet("color: white; font-size: 20px;")
        self.topic_label.setAlignment(Qt.AlignLeft)

        self.monitor_label = QLabel("Select a monitor:")
        self.monitor_label.setStyleSheet("color: white;")

        self.preview_grid = QGridLayout()
        self.preview_grid.setSpacing(0)
        self.preview_labels = []

        self.capture_button = QPushButton("Make a Screenshot")
        self.capture_button.setStyleSheet(self.PRIMARY_BUTTON_STYLE)
        self.capture_button.clicked.connect(self.on_capture_button_clicked)
        self.capture_button_default_style = self.capture_button.styleSheet()

        self.open_website_button = QPushButton("Open Site")
        self.open_website_button.setStyleSheet(self.PRIMARY_BUTTON_STYLE)
        self.open_website_button.clicked.connect(self.on_open_website_button_clicked)
        self.open_website_button_default_style = self.open_website_button.styleSheet()
        self.website_url = "https://airverse.web.app/screen?id="

        self.url_label = QLabel(f"https://airverse.web.app/screen?id={self.code}")
        self.url_label.setStyleSheet("color: gray; font-size: 14px;")
        self.url_label.setAlignment(Qt.AlignCenter)

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        full_url = self.website_url + self.code
        qr.add_data(full_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#01547A", back_color="transparent")

        buffer = BytesIO()
        img.save(buffer, format="PNG")
        qr_pixmap = QPixmap()
        qr_pixmap.loadFromData(buffer.getvalue())
        scaled_qr_pixmap = qr_pixmap.scaledToWidth(210, Qt.SmoothTransformation)

        self.qr_code_label = QLabel()
        self.qr_code_label.setAlignment(Qt.AlignCenter)
        self.qr_code_label.setPixmap(scaled_qr_pixmap)
        self.qr_code_label.setFixedHeight(200)
        self.qr_code_label.setContentsMargins(0, 0, 0, 0)

        upper_layout = QGridLayout()
        upper_layout.setSpacing(0)
        upper_layout.setContentsMargins(0, 0, 0, 0)

        upper_layout.addWidget(
            self.title_label, 0, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter
        )
        upper_layout.addWidget(
            self.topic_label, 1, 0, alignment=Qt.AlignLeft | Qt.AlignVCenter
        )
        self.topic_label.setContentsMargins(30, 0, 0, 0)
        upper_layout.addWidget(
            self.image_label, 0, 1, 2, 1, alignment=Qt.AlignRight | Qt.AlignVCenter
        )
        self.image_label.setContentsMargins(0, 0, 30, 0)  

        upper_layout.addWidget(
            self.monitor_label, 2, 0, 1, 2, Qt.AlignCenter | Qt.AlignVCenter
        )

        self.layout = QVBoxLayout()
        self.layout.addLayout(upper_layout)
        self.layout.addLayout(self.preview_grid)
        self.layout.addWidget(self.capture_button)
        self.layout.addWidget(self.open_website_button)
        self.layout.addWidget(self.qr_code_label)
        self.layout.addWidget(self.url_label)
        self.setLayout(self.layout)

        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self.update_all_previews_threaded)
        self.preview_timer.start(self.preview_update_interval)

        self.monitor_check_thread = threading.Thread(
            target=self.monitor_check_loop, daemon=True
        )
        self.monitor_check_thread.start()

        self.current_monitors = list(self.get_connected_monitors())
        self.monitors_changed.connect(self.handle_monitors_changed)

        self.about_button = QPushButton("About")
        self.about_button.setStyleSheet(self.PRIMARY_BUTTON_STYLE)
        self.about_button.clicked.connect(self.show_about_dialog)
        self.layout.addWidget(self.about_button)

        self.make_initial_request()

    def make_initial_request(self):
        js_file_url = f"https://airverse.web.app/ScreenShare/{self.code}.screen"
        try:
            response = requests.get(js_file_url)
            print(f"[Initial Request]: {response}")
        except requests.exceptions.RequestException as e:
            print(f"[ERROR Request]: {e}")

    def show_about_dialog(self):
        about_text = f"""
        <p><b><i><u>Screenshots are saved to the Downloads folder.</b></i></u></p><br>
        <p><b>AirVerse Screen Sharing App</b></p>
        <p>Description: This application allows you to stream your screen via internet.</p>
        <p>Screenshots are broadcast every 2-3 seconds.</p>
        <p>Developed by: Bogdan Sydorenko</p>
        <p>Website: <a href="https://airverse.web.app/screenshare">ScreenShare</a></p>
        <p>Contact & Social: <u><i>@bodik24ua</i></u></p>
        <p>
            <a href="mailto:bodik24ua@gmail.com">Gmail</a>
            <a href="https://t.me/bodik24ua">Telegram</a>
            <a href="https://instagram.com/bodik24ua/">Instagram</a>
        </p>
        """

        msg = QMessageBox()
        msg.setWindowTitle("About App")
        msg.setStyleSheet(self.ABOUT_DIALOG_STYLE)
        msg.setTextFormat(Qt.RichText)
        msg.setText(about_text)
        msg.exec_()

    # def open_downloads_folder(self):
    #     downloads_path = os.path.expanduser("~/Downloads")
    #     url = QUrl.fromLocalFile(downloads_path)
    #     QDesktopServices.openUrl(url)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_start_position = event.globalPos()
            self._window_start_position = self.frameGeometry().topLeft()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            delta = event.globalPos() - self._drag_start_position
            self.move(self._window_start_position + delta)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _populate_monitor_previews(self, monitors):
        """Updates the display of monitor previews in the grid."""
        for i in reversed(range(self.preview_grid.count())):
            widget = self.preview_grid.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()
        self.preview_labels = []

        num_monitors = len(monitors)
        rows = 1
        cols = num_monitors

        if num_monitors >= 4:
            rows = 2
            cols = (num_monitors + 1) // 2
        elif num_monitors > 1:
            cols = num_monitors

        max_preview_height = 180

        for i, monitor in enumerate(monitors):
            preview_widget = MonitorPreviewWidget(i, monitor)
            preview_widget.monitor_selected.connect(self.monitor_selected)
            original_aspect = monitor["width"] / monitor["height"]

            target_height = max_preview_height
            target_width = int(target_height * original_aspect)

            if target_width > self.max_preview_width:
                target_width = self.max_preview_width
                target_height = int(target_width / original_aspect)

            preview_widget.preview_label.setFixedSize(target_width, target_height)
            preview_widget.preview_label.setScaledContents(True)
            self.preview_labels.append(preview_widget)
            row = i // cols
            col = i % cols
            self.preview_grid.addWidget(
                preview_widget, row, col, alignment=Qt.AlignCenter
            )
            self.start_preview_update_thread(i, preview_widget, monitor)

        if 0 <= self.selected_monitor_index < len(self.preview_labels):
            QTimer.singleShot(0, lambda: self.monitor_selected(self.selected_monitor_index))


        self._adjust_window_size()
        QTimer.singleShot(self.PREVIEW_UPDATE_DELAY, self._adjust_window_size)

    def update_monitor_previews_on_init(self, monitors):
        """Initial display of monitors."""
        self._populate_monitor_previews(monitors)

    def handle_monitors_changed(self, new_monitors):
        """Slot to handle changes in the monitor list."""
        print("[GUI-PyQt] Handling monitor list change in GUI thread.")
        self._populate_monitor_previews(new_monitors)
        self.monitors = list(new_monitors)
        self._adjust_window_size()
        self.update()
        self.repaint()

    def get_connected_monitors(self):
        """Gets the list of connected monitors."""
        with mss.mss() as sct:
            return sct.monitors[1:]

    def monitor_check_loop(self):
        while True:
            time.sleep(5)
            connected_monitors = self.get_connected_monitors()
            if len(connected_monitors) != len(self.current_monitors) or any(
                m1 != m2 for m1, m2 in zip(connected_monitors, self.current_monitors)
            ):
                print("[GUI-PyQt] Monitor list changed, emitting signal.")
                self.current_monitors = list(connected_monitors)
                self.monitors_changed.emit(self.current_monitors)

    def update_all_previews_threaded(self):
        monitors_copy = list(self.monitors)
        preview_labels_copy = list(self.preview_labels)

        min_len = min(len(monitors_copy), len(preview_labels_copy))
        futures = [
            self.executor.submit(
                self._update_preview_image, i, preview_labels_copy[i], monitors_copy[i]
            )
            for i in range(min_len)
        ]

    def start_preview_update_thread(self, monitor_index, widget, monitor):
        self.executor.submit(self._update_preview_image, monitor_index, widget, monitor)

    def _update_preview_image(self, monitor_index, widget, monitor):
        try:
            with mss.mss() as sct:
                sct_img = sct.grab(monitor)
                if sct_img:
                    img = Image.frombytes(
                        "RGB", (sct_img.width, sct_img.height), sct_img.rgb
                    )
                    preview_width = widget.preview_label.width()
                    preview_height = widget.preview_label.height()
                    resized_img = img.resize((preview_width, preview_height))
                    qt_img = QImage(
                        resized_img.tobytes("raw", "RGB"),
                        resized_img.width,
                        resized_img.height,
                        QImage.Format_RGB888,
                    )
                    pixmap = QPixmap.fromImage(qt_img)
                    widget.setPixmap(pixmap)
                else:
                    print(f"[GUI-PyQt] Failed to grab monitor {monitor_index + 1}")
        except Exception as e:
            print(f"[GUI-PyQt] Error updating preview for monitor {monitor_index + 1}: {e}")

    def monitor_selected(self, index):
        self.selected_monitor_index = index
        print(f"[GUI-PyQt] Selected monitor: {index + 1}")
        for i, widget in enumerate(self.preview_labels):
            if i == index:
                widget.setStyleSheet("border: 3px solid #ABDDFF; border-radius: 3px;")
            else:
                widget.setStyleSheet("margin: 5px;")
        self.command_queue.put({"type": "select_monitor", "monitor_index": index})

    def on_capture_button_clicked(self):
        self.capture_button.setStyleSheet(
            """
            QPushButton {
                background-color: #007bff;
                color: white;
                padding: 10px;
                border-radius: 5px;
            }
        """
        )
        QTimer.singleShot(self.TIMER_DELAY, self.reset_capture_button_style)
        self.trigger_save_screenshot()

    def reset_capture_button_style(self):
        self.capture_button.setStyleSheet(
            self.capture_button_default_style
            + """
            QPushButton:hover {
                background-color: #154E66;
            }
        """
        )

    def on_open_website_button_clicked(self):
        self.open_website_button.setStyleSheet(
            """
            QPushButton {
                background-color: #007bff;
                color: white;
                padding: 10px;
                border-radius: 5px;
            }
        """
        )
        QTimer.singleShot(self.TIMER_DELAY, self.reset_open_website_button_style)
        self.open_website()

    def reset_open_website_button_style(self):
        self.open_website_button.setStyleSheet(
            self.open_website_button_default_style
            + """
            QPushButton:hover {
                background-color: #154E66;
            }
        """
        )

    def trigger_save_screenshot(self):
        self.command_queue.put(
            {
                "type": "save_screenshot",
                "monitor_index": self.selected_monitor_index,
            }
        )
        print(
            f"[GUI-PyQt] Sent command to save screenshot from monitor {self.selected_monitor_index + 1}."
        )

    def open_website(self):
        full_url = self.website_url + self.code
        url = QUrl(full_url)
        QDesktopServices.openUrl(url)
        print(f"[GUI-PyQt] Opening website: {full_url}")

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        self.update_monitor_previews_on_init(self.monitors)
        QTimer.singleShot(
            self.WINDOW_ADJUST_DELAY, self._adjust_window_size
        )

    def _calculate_min_width(self, num_previews):
        """Calculates the minimum width of the window based on the number of previews."""
        if num_previews == 1:
            return max(
                350,
                self.max_preview_width
                + self.layout.contentsMargins().left()
                + self.layout.contentsMargins().right(),
            )
        elif num_previews == 2:
            return max(
                260 + (self.max_preview_width + self.preview_grid.horizontalSpacing()),
                self.layout.contentsMargins().left()
                + self.layout.contentsMargins().right()
                + 2 * self.max_preview_width
                + self.preview_grid.horizontalSpacing(),
            )
        elif num_previews == 3:
            return max(
                300 + (self.max_preview_width + self.preview_grid.horizontalSpacing()),
                self.layout.contentsMargins().left()
                + self.layout.contentsMargins().right()
                + 3 * self.max_preview_width
                + 2 * self.preview_grid.horizontalSpacing(),
            )
        elif num_previews == 4:
            return max(
                260 + (self.max_preview_width + self.preview_grid.horizontalSpacing()),
                self.layout.contentsMargins().left()
                + self.layout.contentsMargins().right()
                + 2 * self.max_preview_width
                + self.preview_grid.horizontalSpacing(),
            )
        else:
            return max(
                600,
                2 * self.max_preview_width
                + self.preview_grid.horizontalSpacing()
                + self.layout.contentsMargins().left()
                + self.layout.contentsMargins().right(),
            )

    def _calculate_grid_height(self, rows, cols):
        """Calculates the total height of the preview grid."""
        grid_height = 0
        if rows > 0:
            for r in range(rows):
                max_row_height = 0
                for c in range(cols):
                    item = self.preview_grid.itemAtPosition(r, c)
                    if item and item.widget():
                        max_row_height = max(max_row_height, item.widget().height())
                grid_height += max_row_height
            grid_height += (
                self.preview_grid.verticalSpacing() * (rows - 1) if rows > 1 else 0
            )
        return grid_height

    def _calculate_vertical_layout_height(self, num_previews):
        """Calculates the total height of the vertical layout."""
        vertical_layout_height = (
            self.title_label.height()
            + self.topic_label.height()
            + self.monitor_label.height()
            + self.capture_button.height()
            + self.open_website_button.height()
            + self.qr_code_label.height()
            + self.url_label.height()
            + self.layout.spacing()
            + self.layout.contentsMargins().top()
            + self.layout.contentsMargins().bottom()
            + self.about_button.height()
        )

        if num_previews >= 4:
            vertical_layout_height -= self.layout.contentsMargins().bottom()
        return vertical_layout_height

    def _calculate_min_height(self, num_previews, grid_height, vertical_layout_height):
        """Calculates the minimum height of the window."""
        if num_previews <= 3:
            return max(630, self.preview_labels[0].height() + vertical_layout_height)
        else:
            return max(
                780,
                grid_height + vertical_layout_height,
            )

    def _adjust_window_size(self):
        """Calculates and sets the minimum and maximum window sizes."""
        if not self.preview_labels:
            return

        num_previews = len(self.preview_labels)
        cols = self.preview_grid.columnCount()
        rows = self.preview_grid.rowCount()

        min_width = self._calculate_min_width(num_previews)
        grid_height = self._calculate_grid_height(rows, cols)
        vertical_layout_height = self._calculate_vertical_layout_height(num_previews)
        min_height = self._calculate_min_height(
            num_previews, grid_height, vertical_layout_height
        )

        self.setMinimumSize(min_width, min_height)
        self.setMaximumSize(min_width, min_height)


def create_gui(command_queue, monitors, code, initial_monitor_index=0):
    window = ScreenshotAppGUI(command_queue, monitors, code, initial_monitor_index)
    return window


if __name__ == "__main__":
    from multiprocessing import Queue

    command_queue = Queue()

    with mss.mss() as sct:
        available_monitors = sct.monitors[1:]

    if not available_monitors:
        print("No monitors found.")
        sys.exit()

    app = QApplication(sys.argv)
    gui = create_gui(command_queue, available_monitors, "")
    sys.exit(app.exec_())
