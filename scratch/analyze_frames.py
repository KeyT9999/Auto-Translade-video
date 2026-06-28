from PIL import Image
import numpy as np

def analyze():
    try:
        orig = Image.open(r"d:\MMO\Auto-Translade-video\scratch\frame_orig.png")
        sub = Image.open(r"d:\MMO\Auto-Translade-video\scratch\frame_sub.png")
    except Exception as e:
        print(f"Error opening images: {e}")
        return
        
    orig_arr = np.array(orig)
    sub_arr = np.array(sub)
    
    print(f"Original shape: {orig_arr.shape}")
    print(f"Subtitled shape: {sub_arr.shape}")
    
    # Calculate difference
    # Shapes are (720, 1280, 3) or (720, 1280, 4)
    # Let's drop alpha channel if it exists
    if orig_arr.shape[2] > 3:
        orig_arr = orig_arr[:, :, :3]
    if sub_arr.shape[2] > 3:
        sub_arr = sub_arr[:, :, :3]
        
    diff = np.abs(orig_arr.astype(int) - sub_arr.astype(int))
    gray_diff = np.mean(diff, axis=2)
    
    # Find rows where there is a difference
    row_diffs = np.sum(gray_diff > 10, axis=1)
    modified_rows = np.where(row_diffs > 0)[0]
    
    if len(modified_rows) == 0:
        print("No differences found.")
        return
        
    start_row = modified_rows[0]
    end_row = modified_rows[-1]
    print(f"Modified rows: from {start_row} to {end_row} (out of {orig_arr.shape[0]})")
    
    print("\nRow analysis in sub:")
    for r in range(0, 720, 40):
        avg_color = np.mean(sub_arr[r, :, :], axis=0)
        print(f"Row {r}: Average RGB: {avg_color}")
        
    # Let's find newly darkened rows (where orig was relatively bright but sub became very dark)
    low_val_rows = []
    for r in range(orig_arr.shape[0]):
        avg_orig = np.mean(orig_arr[r, :, :])
        avg_sub = np.mean(sub_arr[r, :, :])
        # If row average in sub is less than 30 and it decreased significantly from orig
        if avg_sub < 40 and (avg_orig - avg_sub) > 20:
            low_val_rows.append(r)
            
    if low_val_rows:
        print(f"Newly darkened rows: from {low_val_rows[0]} to {low_val_rows[-1]}")
    else:
        print("No newly darkened rows found.")

if __name__ == "__main__":
    analyze()
