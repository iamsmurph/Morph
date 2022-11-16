import streamlit as st
import pandas as pd
import numpy as np
import time
import matplotlib.pyplot as plt
from tqdm import tqdm
from scipy import ndimage
import pickle
from sklearn.preprocessing import MinMaxScaler
import io

st.title("OrgSym")

st.markdown("Please input the coordinates of the organoids to be optimized.")

def get_features(mask, centroids):
        # generate pattern
        msg = st.empty()
        msg.markdown("Generating patterns...")
        im = make_pattern(mask, centroids, fillVal = 255)
        msg.markdown("Done")
        
        msg = st.empty()
        msg.markdown("Gaussian blurring...")
        im_blurs = []
        my_bar = st.progress(10)
        sigmas = [200, 700]
        for i, sigma in enumerate(sigmas): #tqdm
            blur = ndimage.gaussian_filter(im, sigma=sigma, mode = 'constant')
            im_blurs.append(blur)
            percent_done = int(((i+1)/len(sigmas)))*100
            my_bar.progress(percent_done)
        msg.markdown("Done")

        msg = st.empty()
        msg.markdown("Computing features...")
        my_bar = st.progress(10)
        grad_rho200 = compute_feats(im, im_blurs[0], centroids, rho = False)
        my_bar.progress(50)
        rho700 = compute_feats(im, im_blurs[1], centroids, grad_rho = False)
        my_bar.progress(100)
        msg.markdown("Done")

        feats = np.array(list(zip(rho700, grad_rho200)))
        return feats

        
def compute_feats(im, im_blur, centroids, rho = True, grad_rho = True):
    feats = []
    for x, y in centroids:
        
        bool_mat = circle(x,y, im, org_rad)

        dfeats = im_blur[bool_mat]
        if rho and not grad_rho:
            density = np.mean(dfeats)
            feats.append(density)
        if not rho and grad_rho:
            grad, _ = max_gradient(x,y, im_blur)
            feats.append(grad)
        if rho and grad_rho:
            feats.append((density, grad))
    return feats
            

def max_gradient(x,y, im_blur):
    # get pixel intensities in extremes
    xmax = im_blur[x + org_rad - 1, y]
    xmin = im_blur[x - org_rad, y]
    ymax = im_blur[x, y + org_rad - 1]
    ymin = im_blur[x, y - org_rad]

    xdiffnorm  = ((xmax - xmin) / org_rad)
    ydiffnorm = ((ymax - ymin) / org_rad)

    # gradient magnitude and vector
    grad = np.array(np.sqrt(xdiffnorm**2 + ydiffnorm**2))
    gradVec = np.array((xdiffnorm, ydiffnorm))
                
    return grad, gradVec

def make_pattern(mask, centroids, fillVal = 255):
    for x,y in centroids:
        dim = len(mask)
        xx, yy = np.mgrid[:org_rad*2, :org_rad*2]
        zz = (xx - org_rad) ** 2 + (yy - org_rad) ** 2
        circle = zz < org_rad ** 2
        bool_mat = np.pad(circle, ((x-org_rad, dim-x-org_rad),(y-org_rad, dim-y-org_rad)))
        mask[bool_mat] = fillVal
    return mask

def make_plot(mask, centroids, preds):
    scaler = MinMaxScaler(feature_range=(0, 255))
    preds_norm = scaler.fit_transform(preds)
    for (x,y), pred in zip(centroids, preds_norm):
        dim = len(mask)
        xx, yy = np.mgrid[:org_rad*2, :org_rad*2]
        zz = (xx - org_rad) ** 2 + (yy - org_rad) ** 2
        circle = zz < org_rad ** 2
        bool_mat = np.pad(circle, ((x-org_rad, dim-x-org_rad),(y-org_rad, dim-y-org_rad)))
        mask[bool_mat] = pred
    return mask

def circle(x,y, orgIm, radius, fill = False, fillVal = 255):
    dim = len(orgIm)
    xx, yy = np.mgrid[:radius*2, :radius*2]
    zz = (xx - radius) ** 2 + (yy - radius) ** 2
    circle = zz < radius ** 2
    
    bool_mat = np.pad(circle, ((x-radius, dim-x-radius),(y-radius, dim-y-radius)))
    if fill:
        orgIm[bool_mat] = fillVal
        return orgIm
    else:
        return bool_mat

#size = st.number_input('Input mask size:')
uploaded_file = st.file_uploader("Upload organoid coordinates (.csv format):")
#size = int(size)

if uploaded_file is not None:
    centroids = pd.read_csv(uploaded_file).values.astype(int)
    
    org_rad = 75
    model_path = "models/krr_model.checkpoint"

    pad = 1000
    cmin = centroids.min()
    if cmin != pad:
        diff = pad - cmin
        centroids += diff
    
    size = int(centroids.max() + pad)
    mask = np.zeros((size, size))
    feats = get_features(mask, centroids)

    scaler = MinMaxScaler()
    X = scaler.fit_transform(feats)

    loaded_model = pickle.load(open(model_path, 'rb'))
    preds = loaded_model.predict(X)
    preds = preds.reshape(-1, 1)
    scaler = MinMaxScaler(feature_range=(0,1))
    preds_norm = scaler.fit_transform(preds)

    arr = np.hstack([centroids, feats, preds_norm])
    cols = ["cx", "cy","density_700","grad_200","pred"]
    res_df = pd.DataFrame(arr, columns = cols)
    @st.cache
    
    def convert_df(df):
        return df.to_csv().encode('utf-8')
    st.subheader("Prediction Table")
    csv = convert_df(res_df)
    st.write(res_df)
    st.download_button(
        "Download",
        csv,
        "result_table.csv",
        "text/csv",
        key='download-csv'
    )

    st.subheader("Prediction Plot")
    mask = np.zeros((size, size))
    res_plot = make_plot(mask, centroids, preds_norm)

    fig, ax = plt.subplots()
    im = ax.imshow(res_plot)
    plt.colorbar(im)
    plt.title("Dipole Prediction Plot")
    
    fn = 'result_plot.png'
    img = io.BytesIO()
    plt.savefig(img, format='png')

    st.pyplot(fig)
    
    btn = st.download_button(
        label="Download",
        data=img,
        file_name=fn,
        mime="image/png"
    )