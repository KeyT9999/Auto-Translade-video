from PIL import Image

def crop_images():
    try:
        orig = Image.open(r"d:\MMO\Auto-Translade-video\scratch\frame_orig.png")
        sub = Image.open(r"d:\MMO\Auto-Translade-video\scratch\frame_sub.png")
        
        # Crop from y=450 to 720, x=300 to 980
        box = (300, 450, 980, 720)
        
        crop_orig = orig.crop(box)
        crop_sub = sub.crop(box)
        
        crop_orig.save(r"d:\MMO\Auto-Translade-video\scratch\crop_orig.png")
        crop_sub.save(r"d:\MMO\Auto-Translade-video\scratch\crop_sub.png")
        print("Cropped images saved successfully.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    crop_images()
