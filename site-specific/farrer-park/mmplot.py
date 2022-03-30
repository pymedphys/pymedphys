# mmplot.py reads mmresults.csv into dataframe and make a simple boxplot
import matplotlib.pyplot as plt
import pandas as pd

df = pd.read_csv(r"D:\mm\mmresults.csv", sep=",", header=None)
df.columns = ["Date", "PatientID", "Gamma", "Mean Gamma", "Max Gamma"]
print(df)
df.boxplot(column=["Gamma"], fontsize=16)
plt.show()
