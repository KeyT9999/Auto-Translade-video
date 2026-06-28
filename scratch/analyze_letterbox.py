from PIL import Image
import numpy as np

def analyze_letterbox():
    orig = Image.open(r"d:\MMO\Auto-Translade-video\scratch\frame_orig.png")
    arr = np.array(orig)
    if arr.shape[2] > 3:
        arr = arr[:, :, :3]
        
    # Find rows that are NOT black.
    # We can calculate the standard deviation or average intensity of each row.
    # If a row is part of a black bar, its standard deviation across pixels will be very low,
    # and its average color will be very close to black (e.g., < 15).
    row_means = np.mean(arr, axis=(1, 2))
    row_stds = np.std(arr, axis=(1, 2, 3) if arr.ndim == 4 else (1, 2))
    
    # Active rows: mean > 15 or std > 5
    active_rows = np.where((row_means > 15) | (row_stds > 5))[0]
    
    if len(active_rows) == 0:
        print("Entire image is black!")
        return
        
    start_row = active_rows[0]
    end_row = active_rows[-1]
    print(f"Detected active video area: y = {start_row} to {end_row} (out of {arr.shape[0]})")
    print(f"Height of active video: {end_row - start_row + 1} pixels")

if __name__ == "__main__":
    analyze_letterbox()
