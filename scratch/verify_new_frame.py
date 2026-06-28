from PIL import Image
import numpy as np

def verify():
    orig = Image.open(r"d:\MMO\Auto-Translade-video\scratch\frame_orig.png")
    sub = Image.open(r"d:\MMO\Auto-Translade-video\scratch\frame_sub_new.png")
    
    orig_arr = np.array(orig)
    sub_arr = np.array(sub)
    
    if orig_arr.shape[2] > 3:
        orig_arr = orig_arr[:, :, :3]
    if sub_arr.shape[2] > 3:
        sub_arr = sub_arr[:, :, :3]
        
    # Difference
    diff = np.abs(orig_arr.astype(int) - sub_arr.astype(int))
    gray_diff = np.mean(diff, axis=2)
    
    # Check modified rows
    row_diffs = np.sum(gray_diff > 10, axis=1)
    modified_rows = np.where(row_diffs > 0)[0]
    
    print(f"Modified rows: from {modified_rows[0]} to {modified_rows[-1]} (out of {sub_arr.shape[0]})")
    
    # Calculate mask area in pixels:
    # y = ih * 0.85 = 720 * 0.85 = 612.
    # h = ih * 0.12 = 720 * 0.12 = 86.4 -> 86.
    # So y range is 612 to 698.
    # Let's inspect rows 600 to 710 in sub
    print("\nRow analysis in new subtitled frame:")
    for r in range(600, 710, 10):
        avg_color = np.mean(sub_arr[r, :, :], axis=0)
        print(f"Row {r}: Average RGB: {avg_color}")
        
    # Check pixels in the Chinese subtitle region (y=629 to 676, x=400 to 880)
    text_area = sub_arr[629:676, 400:880, :]
    print(f"\nChinese text region in new subtitled frame (y=629-676, x=400-880):")
    print(f"Min pixel value: {np.min(text_area)}")
    print(f"Max pixel value: {np.max(text_area)}")
    print(f"Mean pixel value: {np.mean(text_area)}")
    
    bright_pixels = np.sum(text_area > 10)
    print(f"Number of pixels with intensity > 10: {bright_pixels}")

if __name__ == "__main__":
    verify()
