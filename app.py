import cv2
import os
import zipfile
import numpy as np
from PIL import Image, ImageEnhance
import shutil
from flask import Flask, request, jsonify, send_from_directory, send_file, render_template, make_response
from flask_cors import CORS
import random
import time

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads/'
PROCESSED_FOLDER = 'processed/'
PROCESSED_FILES_FOLDER = os.path.join(PROCESSED_FOLDER, 'processed_files')
UNZIPPED_FOLDER = os.path.join(PROCESSED_FOLDER, 'unzipped')

def ensure_dir_exists(path):
    if not os.path.exists(path):
        os.makedirs(path)

ensure_dir_exists(PROCESSED_FILES_FOLDER)
ensure_dir_exists(UPLOAD_FOLDER)
ensure_dir_exists(PROCESSED_FOLDER)
ensure_dir_exists(UNZIPPED_FOLDER)

def clear_folder(folder_path):
    for filename in os.listdir(folder_path):
        file_path = os.path.join(folder_path, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')

def resize_image(image_path, label_path, output_image_path, output_label_path, target_size=(960, 960)):
    # Load image
    image = cv2.imread(image_path)
    original_height, original_width = image.shape[:2]

    # Resize image
    resized_image = cv2.resize(image, target_size)
    cv2.imwrite(output_image_path, resized_image)

    # Read YOLO label
    with open(label_path, 'r') as file:
        lines = file.readlines()

    resized_labels = []
    for line in lines:
        parts = line.strip().split()
        class_id = parts[0]
        x_center, y_center, width, height = map(float, parts[1:])

        # Convert YOLO format to pixel values
        x_center_pixel = x_center * original_width
        y_center_pixel = y_center * original_height
        width_pixel = width * original_width
        height_pixel = height * original_height

        # Calculate new bounding box in pixel values
        new_x_center_pixel = x_center_pixel * target_size[0] / original_width
        new_y_center_pixel = y_center_pixel * target_size[1] / original_height
        new_width_pixel = width_pixel * target_size[0] / original_width
        new_height_pixel = height_pixel * target_size[1] / original_height

        # Convert back to YOLO format
        new_x_center = new_x_center_pixel / target_size[0]
        new_y_center = new_y_center_pixel / target_size[1]
        new_width = new_width_pixel / target_size[0]
        new_height = new_height_pixel / target_size[1]

        resized_labels.append(f"{class_id} {new_x_center} {new_y_center} {new_width} {new_height}\n")

    # Write resized labels to file
    with open(output_label_path, 'w') as file:
        file.writelines(resized_labels)
    print(f"Resized image saved to {output_image_path}")

def mirror_image_and_labels(image_path, label_path, output_image_path, output_label_path):
    img = Image.open(image_path)
    mirrored_img = img.transpose(Image.FLIP_LEFT_RIGHT)
    mirrored_img.save(output_image_path)
    img.close()

    with open(label_path, 'r') as f:
        lines = f.readlines()

    width, height = img.size

    new_lines = []
    for line in lines:
        parts = line.strip().split()
        class_id = parts[0]
        x_center = float(parts[1])
        y_center = float(parts[2])
        width_bbox = float(parts[3])
        height_bbox = float(parts[4])

        new_x_center = 1 - x_center
        new_line = f"{class_id} {new_x_center} {y_center} {width_bbox} {height_bbox}\n"
        new_lines.append(new_line)

    with open(output_label_path, 'w') as f:
        f.writelines(new_lines)

def add_gaussian_noise(image, mean=0, std=0.1, seed=None):
    if seed is not None:
        np.random.seed(seed)
    np_image = np.array(image)
    gaussian = np.random.normal(mean, std, np_image.shape)
    noisy_image = np.clip(np_image + gaussian * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(noisy_image)

def random_brightness(image, factor1=1.0, factor2=1.0, seed=None):
    if seed is not None:
        np.random.seed(seed)
    enhancer = ImageEnhance.Brightness(image)
    factor1 = random.uniform(factor1, factor2)
    return enhancer.enhance(factor1)

def random_saturation(image, factor1=1.0, factor2=1.0, seed=None):
    if seed is not None:
        np.random.seed(seed)
    enhancer = ImageEnhance.Color(image)
    factor1 = random.uniform(factor1, factor2)
    return enhancer.enhance(factor1)

def rotate_image_and_labels(image_path, label_path, output_image_path, output_label_path, angle):
    if angle not in [90, 180, 270]:
        raise ValueError("Rotation angle must be 90, 180, or 270 degrees")
    
    img = Image.open(image_path)
    rotated_img = img.rotate(angle, expand=True)
    rotated_img.save(output_image_path)
    img.close()
    print(f"Rotated image saved to {output_image_path}")
    
    with open(label_path, 'r') as f:
        lines = f.readlines()

    width, height = img.size

    new_lines = []
    for line in lines:
        parts = line.strip().split()
        class_id = parts[0]
        x_center = float(parts[1])
        y_center = float(parts[2])
        width_bbox = float(parts[3])
        height_bbox = float(parts[4])

        if angle == 90:
            new_x_center = y_center
            new_y_center = 1 - x_center
            new_width_bbox = height_bbox
            new_height_bbox = width_bbox
        elif angle == 180:
            new_x_center = 1 - x_center
            new_y_center = 1 - y_center
            new_width_bbox = width_bbox
            new_height_bbox = height_bbox
        elif angle == 270:
            new_x_center = 1 - y_center
            new_y_center = x_center
            new_width_bbox = height_bbox
            new_height_bbox = width_bbox

        new_line = f"{class_id} {new_x_center} {new_y_center} {new_width_bbox} {new_height_bbox}\n"
        new_lines.append(new_line)

    with open(output_label_path, 'w') as f:
        f.writelines(new_lines)
    print(f"Rotated labels saved to {output_label_path}")

def unzip_file(zip_src, dst_dir):
    with zipfile.ZipFile(zip_src, 'r') as zip_ref:
        zip_ref.extractall(dst_dir)

def zip_folder(folder_path, output_path):
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk(folder_path):
            for file in files:
                if not file.startswith('temp'):
                    zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), folder_path))

@app.route('/')
def index():
    response = make_response(render_template('index.html'))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

def clear_upload_folder():
    for filename in os.listdir(UPLOAD_FOLDER):
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        try:
            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')
            
@app.route('/upload', methods=['POST'])
def upload():
    # Clear the upload folder before saving new files
    clear_upload_folder()

    files = request.files.getlist('files')
    for file in files:
        filename = file.filename
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        
        # Ensure directory exists
        ensure_dir_exists(os.path.dirname(file_path))
        
        file.save(file_path)
    
    # Assuming the uploaded folder or zip file is saved
    dataset_filename = "uploaded_dataset.zip"
    zip_folder(UPLOAD_FOLDER, os.path.join(PROCESSED_FOLDER, dataset_filename))
    
    return jsonify({"message": "Files uploaded successfully", "datasetFilename": dataset_filename}), 200

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    response = make_response(send_from_directory(UPLOAD_FOLDER, filename))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

@app.route('/process', methods=['POST'])
def process():
    data = request.json
    options = data.get('options', {})
    dataset_filename = data.get('datasetFilename', '')

    print(f"Received options: {options}")
    print(f"Received dataset filename: {dataset_filename}")
    
    if not dataset_filename:
        return jsonify({"error": "No dataset filename provided"}), 400

    dataset_path = os.path.join(PROCESSED_FOLDER, dataset_filename)
    unzip_dir = UNZIPPED_FOLDER
    
    ensure_dir_exists(unzip_dir)
    ensure_dir_exists(PROCESSED_FILES_FOLDER)

    # Clear the unzipped and processed_files directory
    clear_folder(unzip_dir)
    clear_folder(PROCESSED_FILES_FOLDER)

    unzip_file(dataset_path, unzip_dir)
    print(f"Unzipped dataset to {unzip_dir}")

    for root, dirs, files in os.walk(unzip_dir):
        for file in files:
            if file.endswith(('.png', '.jpg', '.jpeg')):
                original_img_path = os.path.join(root, file)
                original_label_path = os.path.splitext(original_img_path)[0] + '.txt'
                final_img_path = os.path.join(PROCESSED_FILES_FOLDER, file)
                final_label_path = os.path.join(PROCESSED_FILES_FOLDER, os.path.splitext(file)[0] + '.txt')

                # Create a temporary path for intermediate processing steps
                temp_img_path = os.path.join(PROCESSED_FILES_FOLDER, f"temp_{file}")
                temp_label_path = os.path.join(PROCESSED_FILES_FOLDER, f"temp_{os.path.splitext(file)[0]}.txt")

                current_img_path = original_img_path
                current_label_path = original_label_path

                if options.get('sequence'):
                    sequence = options['sequence']
                    for step in sequence:
                        if step['step'] == 'Rotate':
                            angle = int(step['params'].get('angle', 90))
                            print(f"Rotating image by {angle} degrees")
                            if angle not in [90, 180, 270]:
                                return jsonify({"error": "Invalid rotation angle. Must be 90, 180, or 270 degrees."}), 400
                            rotate_image_and_labels(current_img_path, current_label_path, temp_img_path, temp_label_path, angle)
                            current_img_path, current_label_path = temp_img_path, temp_label_path

                        elif step['step'] == 'Mirror':
                            print(f"Adding Mirror")
                            mirror_image_and_labels(current_img_path, current_label_path, temp_img_path, temp_label_path)
                            current_img_path, current_label_path = temp_img_path, temp_label_path

                        elif step['step'] == 'Add Noise':
                            img = Image.open(current_img_path)
                            noise_type = step['params'].get('type', 'Gaussian')
                            print(f"Adding noise: {noise_type}")
                            if noise_type == 'Gaussian':
                                mean = float(step['params'].get('mean', 0))
                                std = float(step['params'].get('std', 0.1))
                                print(f"Gaussian noise params: mean={mean}, std={std}")
                                img = add_gaussian_noise(img, mean, std, seed=42)
                            elif noise_type == 'Brightness':
                                factor1 = float(step['params'].get('factor1', 1.0))
                                factor2 = float(step['params'].get('factor2', 1.0))
                                print(f"Brightness factors: factor1={factor1}, factor2={factor2}")
                                img = random_brightness(img, factor1, factor2, seed=42)
                            elif noise_type == 'Saturation':
                                factor1 = float(step['params'].get('factor1', 1.0))
                                factor2 = float(step['params'].get('factor2', 1.0))
                                print(f"Saturation factors: factor1={factor1}, factor2={factor2}")
                                img = random_saturation(img, factor1, factor2, seed=42)
                            img.save(temp_img_path)
                            img.close()
                            current_img_path = temp_img_path

                        elif step['step'] == 'Resize':
                            img = Image.open(current_img_path)
                            width = int(step['params'].get('width', 960))
                            height = int(step['params'].get('height', 960))
                            print(f"Resizing image to {width}x{height}")
                            resize_image(current_img_path, current_label_path, temp_img_path, temp_label_path, (width, height))
                            current_img_path, current_label_path = temp_img_path, temp_label_path

                # After all processing steps, save the final result with the original filename
                shutil.copy(current_img_path, final_img_path)
                if os.path.exists(current_label_path):
                    shutil.copy(current_label_path, final_label_path)
                    print(f"Final image saved to {final_img_path}")

                # Clean up temporary files immediately after use
                if os.path.exists(temp_img_path):
                    try:
                        os.remove(temp_img_path)
                    except PermissionError:
                        print(f"Could not delete temporary file {temp_img_path} because it is being used by another process.")
                if os.path.exists(temp_label_path):
                    try:
                        os.remove(temp_label_path)
                    except PermissionError:
                        print(f"Could not delete temporary file {temp_label_path} because it is being used by another process.")

    # Ensure no temp files are in the processed files folder
    for root, dirs, files in os.walk(PROCESSED_FILES_FOLDER):
        for file in files:
            if file.startswith('temp'):
                try:
                    os.remove(os.path.join(root, file))
                except PermissionError:
                    print(f"Could not delete temporary file {file} because it is being used by another process.")

    processed_dataset_filename = "processed_dataset.zip"
    processed_dataset_path = os.path.join(PROCESSED_FOLDER, processed_dataset_filename)
    zip_folder(PROCESSED_FILES_FOLDER, processed_dataset_path)
    print(f"Zipped processed dataset to {processed_dataset_path}")

    return jsonify({"message": "Images processed successfully", "datasetFilename": processed_dataset_filename}), 200

@app.route('/download/<filename>')
def download_file(filename):
    full_path = os.path.join(PROCESSED_FOLDER, filename)
    response = make_response(send_file(full_path, as_attachment=True))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

if __name__ == '__main__':
    app.run(debug=True)
