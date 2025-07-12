# Writing and Contributing a Tutorial to PyMedPhys

_Contributed by Anushikha Bhogiya_

Hi!  
If you're new to open source and want to contribute something meaningful, writing a tutorial for PyMedPhys is a great place to begin. 
I'm writing this as someone who's also just started — so I’ll keep everything simple and to the point, the way I wish I had when I began.

---

So, what You’ll Need Before Starting

- A GitHub account
- Some basic Python knowledge
- Basic idea of how Markdown works (don’t worry about it if right now you don’t have any idea)

#make sure you have them before going to the steps as we will learn it by doing

---

## Step 1: Understand What Kind of Tutorial You’re Writing:

PyMedPhys’s documentation is based on a system called “Diátaxis”. You don’t need to go deep into it, but just know this:

There are four types of docs:
- Tutorials (learning by doing)
- How-to guides (doing something specific)
- Reference (facts, commands, syntax)
- Explanation (concepts, theory)

What we’re focusing on is a "tutorial" — so just imagine you’re helping someone do something from scratch, step by step.

It doesn’t have to be perfect. It just needs to work and make sense to someone who is new to it.

> And if you're curious and want to read more about Diátaxis, you can check this out: [https://diataxis.fr/](https://diataxis.fr/)

---

## Step 2: Choose a Topic

Pick something you understand well and can explain simply. Here are a few ideas:

- Installing PyMedPhys and checking if it works
- Loading and displaying a DICOM(a standard format for storing and exchanging medical images and related information) file
- Any small workflow that helped you when learning

and even if you feels its very basic — trust me, it’ll help someone, and that person will help you later.

---

## Step 3: Write Your Tutorial

# Folder and File Setup:

1. Fork the repo: [https://github.com/pymedphys/pymedphys](https://github.com/pymedphys/pymedphys)
2. Clone it and create a file in this path:  
3. Name it something simple like `getting-started.md` or `first-contribution.md`

you can use this Template:

```markdown (Markdown is a simple way to format text in files like tutorials or readmes.)
# [Title of Your Tutorial]

# What Will You Learn?

Write in one line what the user will be able to do after finishing this tutorial.  
Example: "You will learn how to run a basic gamma evaluation using PyMedPhys." (don’tworry about the topic if you don’tknow what gamma is.) 

---

# What You Need Before Starting

Make sure you have these things ready:

- Python installed (any version like 3.8 or above)
- PyMedPhys installed  
  → To install it, just open your terminal or command prompt and run this:

  ```bash
  pip install pymedphys

- Extra Files (if needed)

If your tutorial needs any files (like DICOM files, data files, or example inputs), mention them clearly here.

For example:

- This tutorial uses a DICOM file called `example.dcm`.  
You can download it from this link: [your-download-link-here]  
OR  
If it's already in the repo, just mention the path like this: `data/example.dcm`

Also, make sure to include how to load it in your code like:

```python
import pydicom
ds = pydicom.dcmread("example.dcm")

---

## Step-by-Step Guide

# Step 1: Import the library

```python
import pymedphys

# Step 2: Define your input files (reference and evaluation)

reference_path = "data/reference.dcm"
evaluation_path = "data/evaluation.dcm"

# Step 3: Set gamma parameters

gamma_options = {
    "dose_percent_threshold": 2,
    "distance_mm_threshold": 2,
    "lower_percent_dose_cutoff": 20,
    "max_gamma": 2,
    "random_subset": 5000
}

# Step 4: Run the gamma evaluation

gamma_result = pymedphys.gamma(
    reference_path,
    evaluation_path,
    **gamma_options
)

# Step 5: Print the pass rate

import numpy as np

pass_rate = np.sum(gamma_result <= 1) / gamma_result.size
print(f"Pass Rate: {pass_rate * 100:.2f}%")

You’ll get output like: Pass Rate: 97.56% which tells you how many points passed the gamma criteria.

-----

That’s It!

If you reached here, that means you now know how to write and structure a tutorial for PyMedPhys — and maybe even tried running one small task.

It’s okay if you didn’t understand everything at once. What matters is: you tried, and you started.

---

What to Do Next

- Check your tutorial by following it yourself once
- Save it inside the folder: `docs/tutorials/`
- Create a pull request on GitHub
- In your PR message, you can write:

> This tutorial adds a beginner-friendly guide using the Diátaxis model.

After that, project maintainers will help you with reviews and suggestions.

---

# A note from Me

When I started, I had no idea what I was doing.  
But writing this taught me a lot — and gave me the push I needed.

So if you’re also new: it’s okay.  
Just start. That’s enough.

– Anushikha


