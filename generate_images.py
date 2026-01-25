from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os

ASSETS_DIR = 'assets'
if not os.path.exists(ASSETS_DIR):
    os.makedirs(ASSETS_DIR)

def create_gradient_circle(draw, center, radius, color):
    # PIL doesn't do radial gradients easily, so we'll just draw a solid circle with blur
    # Actually, we can just draw a circle on a separate layer and blur it
    pass

def generate_og_image():
    width, height = 1200, 630
    # Background
    img = Image.new('RGB', (width, height), '#020617')
    
    # Draw some "gradients" using blurred ellipses
    overlay = Image.new('RGBA', (width, height), (0,0,0,0))
    draw_overlay = ImageDraw.Draw(overlay)
    
    # Blue glow left
    draw_overlay.ellipse((-200, -200, 400, 400), fill=(59, 130, 246, 50)) # #3B82F6 with low opacity
    # Purple glow right
    draw_overlay.ellipse((width-400, height-400, width+200, height+200), fill=(147, 51, 234, 50)) # #9333EA
    
    # Center glow
    draw_overlay.ellipse((width//2-200, height//2-200, width//2+200, height//2+200), fill=(59, 130, 246, 40))
    
    # Apply blur to overlay
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=100))
    img.paste(overlay, (0,0), overlay)
    
    draw = ImageDraw.Draw(img)
    
    # Grid lines (simplified)
    grid_color = (255, 255, 255, 10)
    for x in range(0, width, 100):
        draw.line([(x, 0), (x, height)], fill=grid_color, width=1)
    for y in range(0, height, 100):
        draw.line([(0, y), (width, y)], fill=grid_color, width=1)
        
    # Main Text
    # Try to load a font, fall back to default if necessary
    try:
        # Try finding a system font or use default
        font_large = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Black.ttf", 100)
        font_sub = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 32)
        font_badge = ImageFont.truetype("/System/Library/Fonts/Supplemental/Courier New Bold.ttf", 20)
    except:
        try:
            font_large = ImageFont.truetype("Arial", 100)
            font_sub = ImageFont.truetype("Arial", 32)
            font_badge = ImageFont.truetype("Arial", 20)
        except:
            font_large = ImageFont.load_default()
            font_sub = ImageFont.load_default()
            font_badge = ImageFont.load_default()

    # Draw Text centered
    text_main = "CURSOR-VIP"
    text_pro = ".PRO"
    
    # Calculate sizes
    # getbbox returns (left, top, right, bottom)
    bbox_main = draw.textbbox((0, 0), text_main, font=font_large)
    w_main = bbox_main[2] - bbox_main[0]
    
    bbox_pro = draw.textbbox((0, 0), text_pro, font=font_large)
    w_pro = bbox_pro[2] - bbox_pro[0]
    
    total_w = w_main + w_pro
    start_x = (width - total_w) // 2
    
    # Draw Main
    draw.text((start_x, 230), text_main, font=font_large, fill='white')
    # Draw Pro (Cyan)
    draw.text((start_x + w_main, 230), text_pro, font=font_large, fill='#22D3EE')
    
    # Subtitle
    text_sub = "AI-FIRST CODE EDITOR MEMBERSHIP"
    bbox_sub = draw.textbbox((0, 0), text_sub, font=font_sub)
    w_sub = bbox_sub[2] - bbox_sub[0]
    draw.text(((width - w_sub) // 2, 360), text_sub, font=font_sub, fill='#94A3B8')
    
    # Badges
    badges = ["Opus 4.5", "GPT-5.2", "Privacy"]
    badge_colors = ['#60A5FA', '#C084FC', '#34D399'] # Blue, Purple, Green
    badge_width = 160
    badge_height = 50
    gap = 30
    total_badge_w = (badge_width * 3) + (gap * 2)
    start_badge_x = (width - total_badge_w) // 2
    badge_y = 450
    
    for i, badge_text in enumerate(badges):
        bx = start_badge_x + i * (badge_width + gap)
        # Draw rounded rect (simulated)
        draw.rectangle([bx, badge_y, bx+badge_width, badge_y+badge_height], outline=badge_colors[i], width=2)
        # Text
        bbox_b = draw.textbbox((0,0), badge_text, font=font_badge)
        wb = bbox_b[2] - bbox_b[0]
        hb = bbox_b[3] - bbox_b[1]
        draw.text((bx + (badge_width-wb)//2, badge_y + (badge_height-hb)//2 - 2), badge_text, font=font_badge, fill=badge_colors[i])

    # Save
    img.save(os.path.join(ASSETS_DIR, 'og.png'))
    print("Generated assets/og.png")

def generate_logo_image():
    size = 512
    img = Image.new('RGBA', (size, size), (0,0,0,0)) # Transparent
    draw = ImageDraw.Draw(img)
    
    # Background Circle (optional, let's keep it transparent or rounded)
    # Let's do a filled circle style like the favicon
    # Draw a blue/purple gradient circle
    # Simple solid for now
    draw.ellipse((20, 20, size-20, size-20), fill='#000000', outline='#3B82F6', width=20)
    
    # Bolt/Flash icon
    # Draw a polygon for a lightning bolt
    # Coordinates for a bolt in 512x512
    center_x, center_y = size//2, size//2
    # Points: top-rightish, center-left, center-right, bottom-leftish
    # Actually bolts are usually: (top-right), (mid-left), (mid-right), (bottom-left) ... zig zag
    
    points = [
        (center_x + 60, 80),  # Top Right
        (center_x - 40, center_y), # Mid Left
        (center_x + 80, center_y), # Mid Right
        (center_x - 60, size - 80), # Bottom Left
        (center_x - 20, size - 80), # Bottom Left adjust
        (center_x + 120, center_y - 40), # Mid Right Lower
        (center_x - 20, center_y - 40) # Mid Left Lower
    ]
    # Simplified bolt:
    # 1. Start top slightly right
    # 2. Go down-left to center
    # 3. Go right
    # 4. Go down-left to bottom tip
    # 5. Go up-right (diagonal)
    # 6. Go left
    # 7. Go up-right to start
    
    bolt_points = [
        (280, 50),
        (180, 260),
        (280, 260),
        (200, 460),
        (380, 200),
        (280, 200),
        (320, 50)
    ]
    
    # Draw Bolt
    draw.polygon(bolt_points, fill='#3B82F6') # Blue bolt
    
    img.save(os.path.join(ASSETS_DIR, 'logo.png'))
    print("Generated assets/logo.png")

if __name__ == "__main__":
    try:
        generate_og_image()
        generate_logo_image()
    except Exception as e:
        print(f"Error: {e}")
