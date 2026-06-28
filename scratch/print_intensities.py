from PIL import Image
import numpy as np

def print_row_intensities():
    orig = Image.open(r"d:\MMO\Auto-Translade-video\scratch\frame_orig.png")
    arr = np.array(orig)
    if arr.shape[2] > 3:
        arr = arr[:, :, :3]
    
    row_means = np.mean(arr, axis=(1, 2))
    
    # Print average intensity for every 20 rows
    for r in range(0, 720, 20):
        print(f"Row {r:03d}: {row_means[r]:.2f}")

if __name__ == "__main__":
    print_row_intensities()
