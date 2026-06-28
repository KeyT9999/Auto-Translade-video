from PIL import Image
import numpy as np

def locate_white_text_sub():
    sub = Image.open(r"d:\MMO\Auto-Translade-video\scratch\frame_sub.png")
    arr = np.array(sub)
    if arr.shape[2] > 3:
        arr = arr[:, :, :3]
        
    white_mask = (arr[:, :, 0] > 200) & (arr[:, :, 1] > 200) & (arr[:, :, 2] > 200)
    white_pixel_coords = np.argwhere(white_mask)
    
    if len(white_pixel_coords) == 0:
        print("No white pixels found in subtitled frame.")
        return
        
    unique_rows, counts = np.unique(white_pixel_coords[:, 0], return_counts=True)
    
    print("Rows with high concentration of white pixels in subtitled frame:")
    for r, count in zip(unique_rows, counts):
        if count > 50:
            print(f"Row {r:03d}: {count} white pixels")

if __name__ == "__main__":
    locate_white_text_sub()
