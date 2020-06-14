# Electron Inserts Program
This setup assumes you have Anaconda Python installed with Python 3.5

## Environment setup
Within a command prompt type the following:

```batch
conda install numpy scipy pandas matplotlib notebook
conda install shapely -c conda-forge
pip install electron_insert_factors
```

## Setting up NBCCC network access
Log into netscaler with the rtpserver user account

In a windows file browser you will then need to navigate to \\nbccc-monaco and
when prompted type in your nbccc windows account. Append nbccc\ in front of
your username to indicate that you are using a nbccc domain account.

## Running the electron insert factors notebook
Within a command prompt change directory to the following:

```batch
S:\ProgrammingRepository\Applications\electron_insert_factor_user_interface
```

Then type the following:

```batch
jupyter notebook
```

The notebook will open in a browser. Electron insert user interface.ipynb is
what you are after.

## Using the notebook
Change the ID to be the patient ID you are searching for. Then select
`Cell > Run All`.

## Updating the electron insert data with a new measurement
The notebook uses the data stored within the following CSV file:

> `S:\Dosimetry\Elekta_EFacs\electron_factor_measured_data.csv`

Update the data by simply appending another item to the end of the spreadsheet.
Make sure it is saved as a csv file.
