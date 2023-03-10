from dataset.MultimodalDataset import MultimodalDataset
from preprocessing import img_preprocessing, ehr_preprocessing, multimodal_preprocessing
import torch
from models.CLIP import CLIP
from models.img_MLP import IMG_MLP
from models.ehr_MLP import EHR_MLP
from loss.CLIPloss import ClipLoss
from tqdm import tqdm
from visualization import plot_metrics
from models import model_checkpoints
torch.manual_seed(0)
device = "cpu" if torch.cuda.is_available() else "cuda"

#loading data
X_img_train_processed, X_ehr_train_processed, y_train = multimodal_preprocessing.load_data('/home/santosh.sanjeev/PE-Research/RadFusion-Dataset/dataset/multimodalpulmonaryembolismdataset/CT_v2/features_train.csv', '/home/santosh.sanjeev/PE-Research/RadFusion-Dataset/dataset/multimodalpulmonaryembolismdataset/new_data_csv/vision&emr_train_ed.csv')
X_img_val_processed, X_ehr_val_processed, y_val = multimodal_preprocessing.load_data('/home/santosh.sanjeev/PE-Research/RadFusion-Dataset/dataset/multimodalpulmonaryembolismdataset/CT_v2/features_val.csv','/home/santosh.sanjeev/PE-Research/RadFusion-Dataset/dataset/multimodalpulmonaryembolismdataset/new_data_csv/vision&emr_val_ed.csv')
X_img_test_processed, X_ehr_test_processed, y_test = multimodal_preprocessing.load_data('/home/santosh.sanjeev/PE-Research/RadFusion-Dataset/dataset/multimodalpulmonaryembolismdataset/CT_v2/features_test.csv', '/home/santosh.sanjeev/PE-Research/RadFusion-Dataset/dataset/multimodalpulmonaryembolismdataset/new_data_csv/vision&emr_test_ed.csv')

X_train_img, X_val_img, X_test_img = X_img_train_processed, X_img_val_processed, X_img_test_processed
X_train_ehr, X_val_ehr, X_test_ehr = ehr_preprocessing.feature_selection(X_ehr_train_processed, y_train, X_ehr_val_processed, X_ehr_test_processed)

# print('hiii', X_train_ehr.shape, type(X_train_ehr), X_train_ehr.dtype)
# print('hellloo', X_train_img.dtype, X_train_img.shape)
X_train_ehr, X_val_ehr, X_test_ehr  = ehr_preprocessing.normalize(X_train_ehr, X_val_ehr, X_test_ehr)

print(X_train_img.dtype, X_train_img.shape, X_val_img.dtype, X_val_img.shape, X_test_img.dtype, X_test_img.shape, X_train_ehr.dtype, X_train_ehr.shape, X_val_ehr.dtype, X_val_ehr.shape, X_test_ehr.dtype, X_test_ehr.shape)

#datasets
train_set = MultimodalDataset(X_train_img, X_train_ehr, y_train)
val_set = MultimodalDataset(X_val_img, X_val_ehr, y_val)
test_set = MultimodalDataset(X_test_img, X_test_ehr, y_test)

#dataloaders
train_loader = torch.utils.data.DataLoader(train_set, batch_size=16, shuffle=True)
val_loader = torch.utils.data.DataLoader(val_set, batch_size=16, shuffle=False)
test_loader = torch.utils.data.DataLoader(test_set, batch_size=16, shuffle=False)

#intialising models
img_model = IMG_MLP()
ehr_model = EHR_MLP()
combined_model = CLIP(img_model, ehr_model)
img_model = img_model.to(device)
ehr_model = ehr_model.to(device)
combined_model = combined_model.to(device)


#specifying loss function and optimizer
criterion = ClipLoss()
optimizer = torch.optim.SGD(combined_model.parameters(), lr=0.1)
scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=60, gamma=0.1)

#train
epochs= 300


valid_loss_min = 20
epochs_list=[]
training_loss=[]
validation_loss=[]
for epoch in range(0, epochs):
    train_loss=0
    test_loss=0
    epochs_list.append(epoch)
    print("epoch number: {0}".format(epoch))
    combined_model.train()
    with tqdm(train_loader, unit = 'batch') as tepoch:
        for batch_idx, (img_train_data, ehr_train_data, train_labels) in enumerate(tepoch):
            img_train_data = img_train_data.to(device)
            ehr_train_data = ehr_train_data.to(device)
            train_labels = train_labels.to(device)

            f1,f2, logits_scale = combined_model.forward(img_train_data.float(), ehr_train_data.float())


            optimizer.zero_grad()
            loss = criterion(f1, f2, logits_scale)
            
            loss.backward()
            optimizer.step()
            #print(logits_scale)
            
            train_loss += loss.item()
    

    with torch.no_grad():
        combined_model.eval()
        with tqdm(val_loader, unit ="batch") as tepoch:
            for batch_idx ,(img_val_data, ehr_val_data, val_labels) in enumerate(tepoch):
                img_val_data = img_val_data.to(device)
                ehr_val_data = ehr_val_data.to(device)
                val_labels = val_labels.to(device)
            
                
                f1,f2, logits_scale = combined_model.forward(img_val_data.float(), ehr_val_data.float())


                loss = criterion(f1, f2, logits_scale)
                
                test_loss+=loss.item()

                


    img_checkpoint = {
        'epoch': epoch + 1,
        'valid_loss_min': test_loss/(batch_idx+1),
        'state_dict': combined_model.visual.state_dict(),
        'optimizer': optimizer.state_dict(),
    }

    ehr_checkpoint = {
        'epoch': epoch + 1,
        'valid_loss_min': test_loss/(batch_idx+1),
        'state_dict': combined_model.text.state_dict(),
        'optimizer': optimizer.state_dict(),
    }

    # save checkpoint
    

    # # ## TODO: save the model if validation loss has decreased
    if  test_loss/(batch_idx+1) <= valid_loss_min:
        # save checkpoint as best model
        model_checkpoints.save_ckp(img_checkpoint, True, './checkpoints/pretrained_img_model.pt')
        model_checkpoints.save_ckp(ehr_checkpoint, True, './checkpoints/pretrained_ehr_model.pt')
        valid_loss_min = test_loss/(batch_idx+1)

    training_loss.append(train_loss/(batch_idx+1))
    validation_loss.append(test_loss/(batch_idx+1))
    print(' train loss: {:.4f} test loss: {:.4f} valid_loss {:.4f}'.format(train_loss/(batch_idx+1),test_loss/(batch_idx+1),valid_loss_min))
    print(logits_scale)
    scheduler.step()


plot_metrics.plot_loss(epochs_list, training_loss,'Training Loss','./visualization/pretraining','training_loss.png')
plot_metrics.plot_loss(epochs_list, validation_loss,'Validation Loss' ,'./visualization/pretraining','validation_loss.png')



