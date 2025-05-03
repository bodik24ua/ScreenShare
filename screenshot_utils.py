from PIL import ImageGrab, Image
import io
import base64
import numpy as np
import mss
import os
from datetime import datetime


class ScreenshotHandler:
    def __init__(self, mqtt_client, selected_monitor=0, max_resolution=(1920, 1080)):
        self.mqtt_client = mqtt_client
        self.last_screenshot_data = None
        self.selected_monitor = selected_monitor
        self.monitor_info = self.get_monitors()
        self.max_resolution = max_resolution
        print(f"[ScreenshotHandler] Initial monitors: {self.monitor_info}")
        print(f"[ScreenshotHandler] Max resolution set to: {self.max_resolution}")

    def get_monitors(self):
        with mss.mss() as sct:
            monitors = sct.monitors[1:]
            print(f"[ScreenshotHandler] Detected monitors: {monitors}")
            return monitors

    def capture(self, monitor=None):
        print(f"[ScreenshotHandler] Attempting to capture with selected_monitor={self.selected_monitor}, provided monitor={monitor}")
        if not self.monitor_info:
            print("[ScreenshotHandler] Error: No monitors available for capture.")
            return None

        monitor_index_to_capture = monitor if monitor is not None else self.selected_monitor
        if not (0 <= monitor_index_to_capture < len(self.monitor_info)):
            print(f"[ScreenshotHandler] Error: Invalid monitor index: {monitor_index_to_capture}, available range: 0 to {len(self.monitor_info) - 1}")
            return None

        with mss.mss() as sct:
            monitor_to_capture = self.monitor_info[monitor_index_to_capture]
            sct_img = sct.grab(monitor_to_capture)
            img = Image.frombytes('RGB', (sct_img.width, sct_img.height), sct_img.rgb)
            return img

    def resize_to_max(self, img, max_width, max_height):
        current_width = img.width
        current_height = img.height

        if current_width <= max_width and current_height <= max_height:
            return img

        width_ratio = max_width / current_width
        height_ratio = max_height / current_height
        scale_factor = min(1.0, width_ratio, height_ratio)

        new_width = int(current_width * scale_factor)
        new_height = int(current_height * scale_factor)

        return img.resize((new_width, new_height))

    def compress_image(self, img, quality):
        img = img.convert('RGB')
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality)
        data = buffer.getvalue()
        return data

    def get_base64(self, img_data):
        return base64.b64encode(img_data).decode('utf-8')

    def capture_and_send(self):
        self.monitor_info = self.get_monitors()
        print(f"[ScreenshotHandler] Capturing and sending from monitor index: {self.selected_monitor}")
        img = self.capture()
        if img:
            img = self.resize_to_max(img, self.max_resolution[0], self.max_resolution[1])

            quality = 90
            img_data = self.compress_image(img, quality)

            reduction_factor = 1.0
            quality_reduction_step = 2
            resolution_reduction_step = 0.02

            while len(img_data) > 400 * 1024 and reduction_factor < 1.2 and quality > 75:
                reduction_factor += resolution_reduction_step
                new_width = int(img.width / reduction_factor)
                new_height = int(img.height / reduction_factor)
                img = img.resize((new_width, new_height))
                print(f"[Screenshot] Reduce resolution to: {img.width}x{img.height} (коеф.: {reduction_factor:.1f})")

                current_quality = quality
                while len(img_data) > 400 * 1024 and current_quality > 75:
                    current_quality -= quality_reduction_step
                    img_data = self.compress_image(img, current_quality)
                    print(f"[Screenshot] Downgrade to: {current_quality}, розмір: {len(img_data)}")

                if len(img_data) <= 400 * 1024:
                    quality = current_quality 
                    break 

            if len(img_data) <= 400 * 1024:
                if self.last_screenshot_data is not None:
                    diff = self.calculate_difference(self.last_screenshot_data, img_data)
                    print(f"[Screenshot] Screen have a difference ({diff:.2f}%)")
                    if diff < 5.0:
                        return

                self.last_screenshot_data = img_data
                base64_image = self.get_base64(img_data)
                self.mqtt_client.send_image(base64_image)
            else:
                print("[Screenshot] Could not compress image to desired size.")

    def calculate_difference(self, img1_data, img2_data):
        img1 = Image.open(io.BytesIO(img1_data)).convert('L')
        img2 = Image.open(io.BytesIO(img2_data)).convert('L')
        img1 = img1.resize(img2.size)
        arr1 = np.array(img1).astype("float")
        arr2 = np.array(img2).astype("float")
        mse = ((arr1 - arr2) ** 2).mean()
        diff_percent = (mse / 255) * 100
        return diff_percent

    def save_screenshot(self, filepath, monitor=None):
        self.monitor_info = self.get_monitors()
        img = self.capture(monitor=monitor)
        if img:
            img = self.resize_to_max(img, self.max_resolution[0], self.max_resolution[1])
            try:
                img = img.convert('RGB')
                img.save(filepath, "JPEG", quality=95)
                print(f"[Screenshot] Saved as: {filepath}")
            except Exception as e:
                print(f"[Screenshot] Error while saving: {e}")
        else:
            print("[Screenshot] Failed to take screenshot to save.")
            self.save_all_monitors_screenshot()

    def save_all_monitors_screenshot(self):
        for i in range(len(self.monitor_info)):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}_monitor_{i + 1}.jpg" 
            downloads_path = os.path.expanduser("~/Downloads")
            filepath = os.path.join(downloads_path, filename)
            self.save_screenshot(filepath, monitor=i)