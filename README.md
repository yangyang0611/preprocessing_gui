# preprocessing_gui
This gui is a no-code preprocessing tools, where user can upload the files and the tool will do the preprocessing automatically

## Upload Folder
Upload a folder include img and label, the label need to follow YOLO label format. There will be a spinner appear when uploading. After successful upload, a pop message will shown up.

## Function
1. Resize
2. Rotate 
    a. 90 degree
    b. 180 degree
    c. 270 degree
3. Mirror
4. Add Noise
    a. Gaussian
        i. mean (range -50~50)
        ii. Standard Deviation (range 0~50)
    b. Brightness
        i. Brightness Factor1 (range -50~50)
        ii. Brightness Factor2 (range -50~50)
    c. Saturation
        i. Saturation Factor1 (range 0.0~2.0)
        ii. Saturation Factor2 (range 0.0~2.0)
    The range is recommend range for each noise. When exceeding the value of range, a warning pop message will shown up and input content is clear.

## Add Step Button
After select the functions, press the `Add Step` button. The functions selected will be shown on the  `Processing Step` area. 

## Processing Steps
You can use drag and drop to adjust the sequence of function steps.

## Proceed Button
Clicked to start the preprocessing, a spinner will shown up indicate the progress is running. 

## Download Dataset
This button is hide from click, only when the preprocessing finished, the button can be click and the dataset is downloaded in zip format. 