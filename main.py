import argparse, os, time
import torch
import random
import torch.backends.cudnn as cudnn
import torch.nn as nn
import torch.optim as optim
from torch.autograd import Variable
from torch.utils.data import DataLoader
from drrn import DRRN
from dataset import DatasetFromHdf5

# Training settings
parser = argparse.ArgumentParser(description="Pytorch DRRN")
parser.add_argument("--batchSize", type=int, default=128, help="Training batch size")
parser.add_argument("--nEpochs", type=int, default=50, help="Number of epochs to train for")
parser.add_argument("--lr", type=float, default=0.1, help="Learning Rate, Default=0.1")
parser.add_argument("--step", type=int, default=5, help="Sets the learning rate to the initial LR decayed by momentum every n epochs, Default=5")
parser.add_argument("--cuda", action="store_true", help="Use cuda?")
parser.add_argument("--resume", default="", type=str, help="Path to checkpoint, Default=None")
parser.add_argument("--start-epoch", default=1, type = int, help="Manual epoch number (useful on restarts)")
parser.add_argument("--clip", type=float, default=0.01, help="Clipping Gradients, Default=0.01")
parser.add_argument("--threads", type=int, default=1, help="Number of threads for data loader to use, Default=1")
parser.add_argument("--momentum", default=0.9, type=float, help="Momentum, Default=0.9")
parser.add_argument("--weight-decay", "--wd", default=1e-4, type=float, help="Weight decay, Default=1e-4")
parser.add_argument("--pretrained", default="", type=str, help='path to pretrained model, Default=None')

def main():
	global opt, model
	opt = parser.parse_args()
	print(opt)

	cuda = opt.cuda
	if cuda  and not torch.cuda.is_available():
		raise Exception("No GPU found, please run without --cuda")

	opt.seed = random.randint(1, 10000)
	print("Random Seed: ", opt.seed)

	cudnn.benchmark = True

	print("===> Loading datasets")
	train_set = DatasetFromHdf5("data/train_291_32_x234.h5")
	training_data_loader = DataLoader(dataset=train_set, num_workers=opt.threads, batch_size=opt.batchSize, shuffle=True)

	print("===> Building model")
	model = DRRN()
	criterion = nn.MSELoss(size_average=False)

	print("===> Setting GPU")
	if cuda:
		model = torch.nn.DataParallel(model).cuda()
		criterion = criterion.cuda()

	# optionally resume from a checkpoint
	if opt.resume:
		if os.path.isfile(opt.resume):
			print("===> loading checkpoint: {}".format(opt.resume))
			checkpoint = torch.load(opt.resume)
			opt.start_epoch = checkpoint["epoch"] + 1
			model.load_state_dict(checkpoint["model"].state_dict())
		else:
			print("===> no checkpoint found at {}".format(opt.resume))

	# optionally copy weights from a checkpoint
	if opt.pretrained:
		if os.path.isfile(opt.pretrained):
			print("===> load model {}".format(opt.pretrained))
			weights = torch.load(opt.pretrained)
			model.load_state_dict(weights['model'].state_dict())
		else:
			print("===> no model found at {}".format(opt.pretrained))

	print("===> Setting Optimizer")
	optimizer = optim.SGD(model.parameters(), lr=opt.lr, momentum=opt.momentum, weight_decay=opt.weight_decay)

	print("===> Training")
	for epoch in range(opt.start_epoch, opt.nEpochs + 1):
		train(training_data_loader, optimizer, model, criterion, epoch)
		save_checkpoint(model, epoch)
		# os.system("python eval.py --cuda --model=model/model_epoch_{}.pth".format(epoch))



def adjust_learning_rate(optimizer, epoch):
	"""Sets the learning rate to the initial LR decayed by 10 every 10 epochs"""
	lr = opt.lr * (0.5 ** (epoch  // opt.step))
	return lr

def train(training_data_loader, optimizer, model, criterion, epoch):
	
	# lr policy
	lr = adjust_learning_rate(optimizer, epoch-1)
	for param_group in optimizer.param_groups:
		param_group["lr"] = lr
	print("Epoch={}, lr={}".format(epoch, optimizer.param_groups[0]["lr"]))

	model.train()

	for iteration, batch in enumerate(training_data_loader, 1):
		input, target = Variable(batch[0]), Variable(batch[1], requires_grad=False)
		if opt.cuda:
			input = input.cuda()
			target = target.cuda()

		loss = criterion(model(input), target)
		optimizer.zero_grad()
		loss.backward()
		# Gradient Clipping
		clip = opt.clip / lr
		nn.utils.clip_grad_norm(model.parameters(), clip)
		optimizer.step()
		if iteration%100 == 0:
			lc_time = time.asctime( time.localtime(time.time()) )
			print("===> {} Epoch[{}]({}/{}): Loss: {:.10f}".format(lc_time, epoch, iteration, len(training_data_loader), loss.data[0]))


def save_checkpoint(model, epoch):
	model_out_path = "model/" + "model_epoch_{}.pth".format(epoch)
	state = {"epoch": epoch, "model": model}
	# check path status
	if not os.path.exists("model/"):
		os.makedirs("model/")
	# save model
	torch.save(state, model_out_path)
	print("Checkpoint saved to {}".format(model_out_path))

if __name__ == "__main__":
	main()
