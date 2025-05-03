import time
import os
from datetime import datetime
from file_manager import load_or_generate_code, save_selected_monitor_index, load_selected_monitor_index
from file_manager import load_or_generate_code
from mqtt_client import MQTTClient
from screenshot_utils import ScreenshotHandler
import gui_pyqt as gui
import queue
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject, pyqtSignal, QThread

DEFAULT_MONITOR_INDEX = 0  

class CaptureThread(QThread):
    def __init__(self, screenshot_handler, command_queue):
        super().__init__()
        self.screenshot_handler = screenshot_handler
        self.command_queue = command_queue
        self._running = True
        self.selected_monitor_index = DEFAULT_MONITOR_INDEX

    def run(self):
        while self._running:
            try:
                command = self.command_queue.get(timeout=0.1)
                if command["type"] == "save_screenshot":
                    monitor_index = command.get("monitor_index", self.selected_monitor_index)
                    self.save_screenshot_to_downloads(monitor_index)
                elif command["type"] == "select_monitor":
                    self.selected_monitor_index = command.get("monitor_index", DEFAULT_MONITOR_INDEX)
                    self.screenshot_handler.selected_monitor = self.selected_monitor_index
                    print(f"[CAPTURE_THREAD] Monitor is selected for capture: {self.selected_monitor_index + 1}")
                    save_selected_monitor_index(self.selected_monitor_index)
            except queue.Empty:
                pass
            self.screenshot_handler.capture_and_send()
            time.sleep(2)
    
    def stop(self):
        self._running = False 
        self.wait()

    def save_screenshot_to_downloads(self, monitor_index):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"Screenshot_{timestamp}_monitor_{monitor_index + 1}.jpg" 
        downloads_path = os.path.expanduser("~/Downloads")
        filepath = os.path.join(downloads_path, filename)
        try:
            self.screenshot_handler.save_screenshot(filepath, monitor=monitor_index)
            print(f"[CAPTURE_THREAD] Screenshot maked from the monitor {monitor_index + 1} and saved to: {filepath}")
        except Exception as e:
            print(f"[CAPTURE_THREAD] Error saving screenshot: {e}")


class App:
    def __init__(self):
        self.code = load_or_generate_code()
        print(f"[APP] Code: {self.code}")
        self.mqtt_client = MQTTClient(self.code)
        self.mqtt_client.connect()
        self.screenshot_handler = ScreenshotHandler(self.mqtt_client)
        self.command_queue = queue.Queue()
        self.gui = None
        self.capture_thread = CaptureThread(self.screenshot_handler, self.command_queue)
        self.capture_thread.selected_monitor_index = load_selected_monitor_index()
        self.mqtt_topic = self.mqtt_client.topic  

    def run(self):
        app = QApplication(sys.argv)
        monitors = self.screenshot_handler.get_monitors()
        self.gui = gui.create_gui(self.command_queue, monitors, self.code, DEFAULT_MONITOR_INDEX)
        self.screenshot_handler.selected_monitor = self.capture_thread.selected_monitor_index
        self.gui.selected_monitor_index = self.capture_thread.selected_monitor_index
        self.gui.show()
        self.capture_thread.start()
        self.gui.monitors_changed.connect(self.update_screenshot_handler_monitors) 
        exit_code = app.exec_()
        self.capture_thread.stop()
        sys.exit(exit_code)

    def update_screenshot_handler_monitors(self, monitors):
        self.screenshot_handler.monitor_info = monitors


if __name__ == "__main__":
    app = App()
    app.run()