$ErrorActionPreference = "Stop"

$version = & python --version 2>&1
if ($version -notmatch "Python 3\.11\.") {
    Write-Error "Este projeto requer o ambiente virtual usando Python 3.11. Atual: $version"
}

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install face-recognition==1.3.0 --no-deps

python -c "import dlib, face_recognition, cv2, numpy, flask; print('Ambiente OK'); print('dlib:', dlib.__version__); print('OpenCV:', cv2.__version__); print('NumPy:', numpy.__version__)"
