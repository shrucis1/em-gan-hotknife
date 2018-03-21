from keras.layers import Conv2D, Conv2DTranspose, UpSampling2D, Dense, Reshape, Flatten, Activation, Input, Lambda
from keras.models import Sequential, load_model
from keras.layers.advanced_activations import LeakyReLU
from keras.losses import binary_crossentropy, mean_squared_error
from keras.optimizers import Adam
from keras.regularizers import L1L2

from keras import backend as K

from models import *
from data_utils import *

import numpy as np
import tensorflow as tf

import os
import pandas
import sys
import argparse


def get_masked_loss(batch_size):

	mask = np.zeros((batch_size, 32, 32, 32, 1), dtype=np.float32)
	mask[:,:7,:,:,:] = 1.0
	mask[:,7,:,:,:] = 0.7
	mask[:,8,:,:,:] = 0.3
	mask[:,-7:,:,:,:] = 1.0
	mask[:,-8,:,:,:] = 0.7
	mask[:,-9,:,:,:] = 0.3

	def masked_loss(y_true, y_pred):
		y_true_masked = tf.multiply(y_true, mask)
		y_pred_masked = tf.multiply(y_pred, mask)
		return mean_squared_error(y_true_masked, y_pred_masked)

	return masked_loss


def main(generator_filename, epochs=25, batch_size=64, num_batches=32,
	disc_lr=1e-7, gen_lr=1e-6, penalty_lr=1e-5, 
	data_file="hotknifedata.hdf5", output_folder="run_output"):

	print("Running em-hotknife GAN training for %d epochs with parameters:" % epochs)
	print("Discriminator LR: %f" % disc_lr)
	print("Generator LR: %f" % gen_lr)
	print("Penalty LR: %f" % penalty_lr)
	print("Outputting data to %s" % output_folder)

	if not os.path.isdir(output_folder):
		os.mkdir(output_folder)

	discriminator = models.get_discriminator()
	discriminator.compile(loss='binary_crossentropy', optimizer=Adam(disc_lr), metrics=['accuracy'])

	generator = load_model(generator_filename)
	generator.name = "pretrained_generator"
	generator.compile(loss='binary_crossentropy', optimizer=Adam(gen_lr)) # Fairly certain this doesn't get directly used anywhere

	penalty_z = Input(shape=(64,64,64,1))
	penalty = Model(penalty_z, generator(penalty_z))
	penalty.compile(loss=get_masked_loss(batch_size), optimizer=Adam(penalty_lr))

	z = Input(shape=(64,64,64,1))
	img = generator(z)

	discriminator.trainable = False

	valid = discriminator(img)

	combined = Model(z, valid)
	combined.compile(loss='binary_crossentropy', optimizer=Adam(gen_lr))

	# for sampling the data for training
	fake_gen = h5_gap_data_generator_valid(data_file,"volumes/data", (64,64,64), batch_size)

	# for training discriminator on what is real
	real_gen = h5_nogap_data_generator(data_file,"volumes/data", (32,32,32), batch_size)

	# just for periodically sampling the generator to see what's going on
	test_gen = h5_gap_data_generator_valid(data_file,"volumes/data", (64,64,64), 5)


	## Just do an "Epoch 0" test
	latent_samp = fake_gen.__next__()
	gen_output = generator.predict(latent_samp)
	real_data = real_gen.__next__()
	d_loss = 0.5 * np.add(discriminator.test_on_batch(real_data, np.ones((batch_size, 1))), discriminator.test_on_batch(gen_output, np.zeros((batch_size, 1))))
	g_loss = combined.test_on_batch(latent_samp, np.ones((batch_size, 1)))
	g_loss_penalty = generator.test_on_batch(latent_samp, get_center_of_valid_block(latent_samp))
	print("Epoch 0 [D loss: %f acc: %f] [G loss: %f penalty: %f]" % (d_loss[0], d_loss[1], g_loss, g_loss_penalty))
	print("="*50)
	## End our Epoch 0 stuff
	## For now, don't bother recording 'epoch 0' in history

	history = {"epoch":[], "d_loss":[], "d_acc":[], "g_loss":[], "g_penalty":[]}

	for epoch in range(epochs):

		g_loss = None
		g_loss_penalty = None
		d_loss = None

		for n in range(num_batches): # do n minibatches

			# train discriminator
			latent_samp = fake_gen.__next__() # input to generator
			gen_output = generator.predict(latent_samp)

			real_data = real_gen.__next__()

			d_loss_real = discriminator.train_on_batch(real_data, np.ones((batch_size, 1)))
			d_loss_fake = discriminator.train_on_batch(gen_output, np.zeros((batch_size, 1)))
			d_loss_new = (1./num_batches) * 0.5 * np.add(d_loss_real, d_loss_fake)

			if d_loss is None:
				d_loss = d_loss_new
			else:
				d_loss = np.add(d_loss, d_loss_new)

			# train generator
			latent_samp = fake_gen.__next__()

			g_loss_new = (1./num_batches) * combined.train_on_batch(latent_samp, np.ones((batch_size, 1)))

			## Now penalty instead of generator
			g_loss_penalty_new = (1./num_batches) * penalty.train_on_batch(latent_samp, get_center_of_valid_block(latent_samp))

			if g_loss is None:
				g_loss = g_loss_new
				g_loss_penalty = g_loss_penalty_new
			else:
				g_loss = np.add(g_loss, g_loss_new)
				g_loss_penalty = np.add(g_loss_penalty, g_loss_penalty_new)

		print("Epoch #%d [D loss: %f acc: %f] [G loss: %f penalty: %f]" % (epoch+1, d_loss[0], d_loss[1], g_loss, g_loss_penalty))

		# now save some sample input
		prev = test_gen.__next__()

		outp = generator.predict(prev)

		write_sampled_output_even(prev, outp, os.path.join(output_folder,"train_epoch_%03d.png"%(epoch+1)))

		if (epoch+1)%5 == 0:
			generator.save(os.path.join(output_folder,"generator_train_epoch_%03d.h5"%(epoch+1)))
			discriminator.save(os.path.join(output_folder,"discriminator_train_epoch_%03d.h5"%(epoch+1)))

		# Update History
		history["epoch"].append(epoch)
		history["d_loss"].append(d_loss[0])
		history["d_acc"].append(d_loss[1])
		history["g_loss"].append(g_loss)
		history["g_penalty"].append(g_loss_penalty)

	generator.save(os.path.join(output_folder,"generator_train_final.h5"))
	discriminator.save(os.path.join(output_folder,"discriminator_train_final.h5"))

	with open(os.path.join(output_folder,"history.csv"),"w") as f:
		pandas.DataFrame(history).reindex(columns=["epochs","d_loss","d_acc","g_loss","g_penalty"]).to_csv(f, index=False)

def generate_argparser():
	parser = argparse.ArgumentParser(description="Train em-hotknife GAN")
	parser.add_argument('-g','--generator', type=str, help="pre-trained generator model (h5) to start training with", required=True)
	parser.add_argument('-df','--datafile', type=str, help="data file (hdf5) to sample from", required=True)
	parser.add_argument('-ne','--epochs', type=int, help="number of epochs to train for", default=50)
	parser.add_argument('-dlr','--disc_lr', type=float, help="discriminator learning rate", required=True)
	parser.add_argument('-glr','--gen_lr', type=float, help="generator learning rate", required=True)
	parser.add_argument('-plr','--penalty_lr', type=float, help="generator deviation penalty learning rate", required=True)
	parser.add_argument('-o','--output', type=str, help="folder/directory to output data to", required=True)
	return parser

if __name__ == "__main__":
	args = generate_argparser().parse_args()
	main(args.generator,
		epochs = args.epochs,
		disc_lr = args.disc_lr,
		gen_lr = args.gen_lr,
		penalty_lr = args.penalty_lr,
		output_folder = args.output,
		data_file = args.datafile
		)
