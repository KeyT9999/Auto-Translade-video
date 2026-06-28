from PIL import Image
import numpy as np

def locate_white_text():
    orig = Image.open(r"d:\MMO\Auto-Translade-video\scratch\frame_orig.png")
    arr = np.array(orig)
    if arr.shape[2] > 3:
        arr = arr[:, :, :3]
        
    # Find pixels that are nearly white (R > 200, G > 200, B > 200)
    white_mask = (arr[:, :, 0] > 200) & (arr[:, :, 1] > 200) & (arr[:, :, 2] > 200)
    white_pixel_coords = np.argwhere(white_mask)
    
    if len(white_pixel_coords) == 0:
        print("No white pixels found in original frame.")
        return
        
    # Group white pixels by row to find where the text blocks are
    unique_rows, counts = np.unique(white_pixel_coords[:, 0], return_counts=True)
    
    print("Rows with high concentration of white pixels (potential subtitles):")
    for r, count in zip(unique_rows, counts):
        if count > 50:  # Only rows with a substantial number of white pixels
            print(f"Row {r:03d}: {count} white pixels")

if __name__ == "__main__":
    locate_white_text()
