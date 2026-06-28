from PIL import Image
import numpy as np

def check_max_values():
    sub = Image.open(r"d:\MMO\Auto-Translade-video\scratch\frame_sub.png")
    arr = np.array(sub)
    if arr.shape[2] > 3:
        arr = arr[:, :, :3]
        
    # Crop the Chinese text area: rows 629 to 676, cols 400 to 880
    text_area = arr[629:676, 400:880, :]
    
    print(f"Subtitled frame - Chinese text area (629-676, 400-880):")
    print(f"Min pixel value: {np.min(text_area)}")
    print(f"Max pixel value: {np.max(text_area)}")
    print(f"Mean pixel value: {np.mean(text_area)}")
    
    # Let's count how many pixels are bright (say, > 100)
    bright_pixels = np.sum(text_area > 100)
    print(f"Number of pixels > 100: {bright_pixels}")

if __name__ == "__main__":
    check_max_values()
