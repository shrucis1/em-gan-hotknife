from keras.layers import Conv2D, Conv2DTranspose, UpSampling2D, Dense, Reshape, Flatten, Activation, Input, Lambda
from keras.models import Sequential
from keras.layers.advanced_activations import LeakyReLU
from keras.losses import binary_crossentropy
from keras.optimizers import Adam
from keras.regularizers import L1L2
from keras import backend as K
from PIL import Image
from scipy.misc import imresize
import numpy as np
import tensorflow as tf
import os
from util import *
from discriminator import *
from generator import *
from data_utils import *


def write_sampled_output(samp, outp, fname, width=16):
	im = np.zeros((320, 32*width), dtype=np.uint8) # cuts at even spacing, 5 samples, plus 5 outputs
	for i in range(5):
		for j in range(width):
			im[64*i:64*i+32,32*j:32*(j+1)] = (samp[i,round(j*32./width),:,:,0]*255).astype(np.uint8)
			im[64*i+32:64*i+64,32*j:32*(j+1)] = (outp[i,round(j*32./width),:,:,0]*255).astype(np.uint8)
	Image.fromarray(imresize(im, 2.0, interp="nearest")).save(fname)

data_folder = "run_output/"

def main(epochs=200, batch_size=64, num_batches=32, lr=1e-5):

	print("Running pretraining with %d epochs, batch size of %d")
	print("Learning rate is %f" % lr)

	if not os.path.isdir(data_folder):
		os.mkdir(data_folder)

	generator = get_generator(shape=(32,32,32))

	generator.compile(loss='binary_crossentropy', optimizer=Adam(lr))

	# for sampling the data for training
	data_gen = h5_nogap_data_generator("hotknifedata.hdf5","volumes/data", (32,32,32), batch_size)

	# just for periodically sampling the generator to see what's going on
	test_gen = h5_nogap_data_generator("hotknifedata.hdf5","volumes/data", (32,32,32), 5)

	train_hist = []

	for epoch in range(epochs):


		g_loss = 0

		for n in range(num_batches):
			samp = data_gen.__next__()
			g_loss += generator.train_on_batch(samp, samp)

		g_loss = g_loss/num_batches

		#g_loss = gen_noedge.train_on_batch(latent_samp, latent_samp)

		print("Epoch #%d [G loss: %f]" % (epoch+1, g_loss))

		train_hist.append(g_loss)

		# now save some sample input
		prev = test_gen.__next__()

		outp = generator.predict(prev)

		write_sampled_output(prev, outp, data_folder+"pretrain_epoch_%03d.png"%(epoch+1))

		generator.save(data_folder+"generator_pretrain_epoch_%03d.h5"%(epoch+1))

if __name__ == "__main__":
	main()
