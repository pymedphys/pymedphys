DATA_PATH_1= /media/matthew/secondary/prostate_dataset_raw/000638
DATA_PATH_2= /media/matthew/secondary/prostate_dataset_raw/002487
DATA_PATH_3= /media/matthew/secondary/prostate_dataset_raw/003887

python pynetdicom storescu 127.0.0.1 34567 $DATA_PATH_1 -v -cx &
sleep 2s
python pynetdicom storescu 127.0.0.1 34567 $DATA_PATH_2 -v -cx &
sleep 2s
python pynetdicom storescu 127.0.0.1 34567 $DATA_PATH_3 -v -cx &
