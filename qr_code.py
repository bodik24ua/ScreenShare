import qrcode
from PIL import Image, ImageTk

def generate_qr_code(data):
    img = qrcode.make(data)
    qr_img = ImageTk.PhotoImage(img)
    return qr_img
