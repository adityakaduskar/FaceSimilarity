# Import relevant Packages
from torch_snippets import *

from torchvision import transforms

device = 'cuda' if torch.cuda.is_available() else 'cpu'

# Create a class for the dataset
class FaceSimilarityDataset(Dataset):
  def __init__(self, folder, transform = None, should_invert = True):
    self.folder = folder
    self.transform = transform
    self.items = Glob(f'{self.folder}/*/*')
  def __getitem__(self, index):
    person_A = self.items[index]
    person = fname(parent(person_A))
    same_person = randint(2)
    if same_person:
      person_B = choose(Glob(f'{self.folder}/{person}/*',\
                             silent=True))
    else:
      while True:
        person_B = choose(self.items)
        if person !=fname(parent(person_B)):
          break
    img_A = read(person_A)
    img_B = read(person_B)
    if self.transform:
      img_A = self.transform(img_A)
      img_B = self.transform(img_B)
      
    return img_A, img_B, np.array([1-same_person])
  def __len__(self):
      return len(self.items)

# Define dataloaders and transforms
train_tf = transforms.Compose([
  transforms.ToPILImage(),
  transforms.RandomHorizontalFlip(),
  transforms.RandomAffine(5, (0.01,0.2), \
  scale=(0.9,1.1)),
  transforms.Resize((100,100)),
  transforms.ToTensor(),
  transforms.Normalize((0.5), (0.5))
])
val_tf = transforms.Compose([
  transforms.ToPILImage(),
  transforms.Resize((100,100)),
  transforms.ToTensor(),
  transforms.Normalize((0.5), (0.5))
])

train_set=FaceSimilarityDataset(folder="SN/data/faces/training/" \
, transform=train_tf)
val_set=FaceSimilarityDataset(folder="SN/data/faces/testing/", \
transform=val_tf)

train_loader = DataLoader(train_set, shuffle=True, batch_size=64)
val_loader = DataLoader(val_set, shuffle=False, batch_size=64)

# Define modular convolutional block
def convBlock(in_channel, out_channel):
  return nn.Sequential(nn.Conv2d(in_channel, out_channel, kernel_size=3, padding =1,\
                                 padding_mode = 'reflect'),
                       nn.ReLU(inplace = True),
                       nn.BatchNorm2d(out_channel),
                       nn.Dropout(0.2)
                       )

# Define Network Architecture
class SiameseNetwork(nn.Module):
  def __init__(self):
    super(SiameseNetwork,self).__init__()
    self.features = nn.Sequential(
        convBlock(1,4),
        convBlock(4,8),
        convBlock(8,8),
        nn.Flatten(),
        nn.Linear(8*100*100, 500), nn.ReLU(inplace=True),
        nn.Linear(500, 500), nn.ReLU(inplace=True),
        nn.Linear(500, 5)
  )
  def forward(self, in_1, in_2):
    out_1 = self.features(in_1)
    out_2 = self.features(in_2)
    return out_1, out_2

# Define class for Contrastive Loss
class ContrastiveLoss(torch.nn.Module):

  def __init__(self, margin=2.0): 
    super(ContrastiveLoss, self).__init__()
    self.margin = margin
  def forward(self, output1, output2,label)  :
    euclidean_distance = F.pairwise_distance(output1, \
                        output2, keepdim = True)
    loss_contrastive = torch.mean((1-label)* \
                        torch.pow(euclidean_distance, 2) + \
                        (label) * torch.pow(torch.clamp(\
                        self.margin - euclidean_distance, \
                        min=0.0), 2))
    acc = ((euclidean_distance>0.6)==label).float().mean()
    return loss_contrastive, acc

def train_batch(model, data, optimizer, criterion):
    imgsA, imgsB, labels = [t.to(device) for t in data]
    optimizer.zero_grad()
    codesA, codesB = model(imgsA, imgsB)
    loss, acc = criterion(codesA, codesB, labels)
    loss.backward()
    optimizer.step()
    return loss.item(), acc.item()

@torch.no_grad()
def validate_batch(model, data, criterion):
    imgsA, imgsB, labels = [t.to(device) for t in data]
    codesA, codesB = model(imgsA, imgsB)
    loss, acc = criterion(codesA, codesB, labels)
    return loss.item(), acc.item()

model = SiameseNetwork().to(device)
criterion = ContrastiveLoss()
optimizer = optim.Adam(model.parameters(),lr = 0.001)

n_epochs = 200
log = Report(n_epochs)
for epoch in range(n_epochs):
    N = len(train_loader)
    for i, data in enumerate(train_loader):
        loss, acc = train_batch(model, data, optimizer, criterion)
        log.record(epoch+(1+i)/N, trn_loss=loss, trn_acc=acc, end='\r')
    N = len(val_loader)
    for i, data in enumerate(val_loader):
        loss, acc = validate_batch(model, data, criterion)
        log.record(epoch+(1+i)/N, val_loss=loss, val_acc=acc, end='\r')
    if (epoch+1)%20==0: log.report_avgs(epoch+1)

log.plot_epochs(['trn_loss','val_loss'])
log.plot_epochs(['trn_acc','val_acc'])

model.eval()
val_dl = DataLoader(val_set,num_workers=6,batch_size=1, \
shuffle=True)
dataiter = iter(val_dl)
x0, _, _ = next(dataiter)
for i in range(2):
  _, x1, label2 = next(dataiter)
  concatenated = torch.cat((x0*0.5+0.5, x1*0.5+0.5),0)
  output1,output2 = model(x0.cuda(),x1.cuda())
  euclidean_distance = F.pairwise_distance(output1, output2)
  output = 'Same Face' if euclidean_distance.item() < 0.6 \
else 'Different'
show(torchvision.utils.make_grid(concatenated), \
  title='Dissimilarity: {:.2f}\n{}'. \
  format(euclidean_distance.item(), output))
plt.show()
