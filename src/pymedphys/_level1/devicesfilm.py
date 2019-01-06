# -*- coding: utf-8 -*-
"""
Created on Tue Apr 21 08:49:00 2015
This is free software, under the terms of the GNU General Public License 
Version 3 (www.gnu.org/licenses) without any implied warranty of 
merchantability or fitness for a particular purpose. 
@author: king.r.paul@gmail.com
"""

import os
import numpy as np
import pylab as plt
import matplotlib.pylab as plt
import matplotlib.image as mpimg

def read_narrow_png(file_name, dpi=600, step_size=0.1):
    """ Does things. """ 

    img = mpimg.imread(file_name)

    # AVG ACROSS PIXELS
    if img.shape[0] > 5*img.shape[1]:   # VERTICAL
        axis = 1
    elif img.shape[1] > 5*img.shape[0]: # HORIZONTAL
        axis = 0     
    else:
        assert False, "not a profile"
    img = np.average(img, axis=axis)   

    # AVG ACROSS COLORS
    img = np.average(img, axis=1)       

    # FIND DISTANCE VALUES FOR FILM
    num_pix = img.shape[0]  # LEN OF FILM IN PIX
    pix_size = (2.54 / dpi) # PIXEL SIZE IN CM
    assert step_size > 5 * pix_size, "not ok to downsample"

    if num_pix % 2 == 0:    # ODD NUM PIX FOR EVEN STEPS
        img = img[:-1]

    film_len = num_pix * pix_size  # FILM LEN IN CM 
    film_distS = np.arange(-film_len/2, film_len/2, pix_size)

    # DOWNSAMPLE FILM
    win = int(step_size/pix_size) # AVERAGING WINDOW IN PIX

    idx = np.arange(win/2, 
                    len(film_distS), 
                    win ).astype(int) # FILM IDX VALUES TO USE
    film_distS =  list(film_distS[idx]) # FILM DIST VALUES TO USE
    
    # AVERAGE FILM DENSITY VALUES OVER THE WINDOW
    density = [] 
    for i in idx: 
        val = np.average( img[int(i-win/2): int(i+win/2)] ) 
        density.append(val)

    result = list(zip(film_distS, density))
    return result

def test_read_narrow_png():
    folder = '.\\tests\\data\\2015_05_26 - TomoCalFilm\\'
    result = read_png_profile(folder + 'FilmCalib_EBT_vert_strip.png')
    result = read_png_profile(folder + 'FilmCalib_EBT_horz_strip.png')
    
if __name__ == "__main__":
    test_read_narrow_png()
