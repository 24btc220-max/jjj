#!/usr/bin/env python3
"""
Fix camera initialization with proper error handling and retry logic
"""

with open('frontend/index.html', 'r') as f:
    content = f.read()

old_func = '''async function initVerifyCamera() {
  testBackend();
  loadFaceAPI(); // preload client-side face-api.js
  try {
    const stream = await navigator.mediaDevices.getUserMedia({video:{width:480,height:360,facingMode:'user'},audio:false});
    const vid = document.getElementById('verify-vid');
    vid.srcObject = stream;
    vid.onloadedmetadata = () => { document.getElementById('vcam-overlay').classList.add('hidden'); document.getElementById('btn-capture').disabled=false; };
  } catch(e) {
    document.getElementById('vcam-overlay').innerHTML='<div>🚫</div><div>Camera denied</div>';
  }
}'''

new_func = '''async function initVerifyCamera() {
  testBackend();
  loadFaceAPI();
  await requestCameraAccess();
}

async function requestCameraAccess() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({video:{width:{ideal:480},height:{ideal:360},facingMode:'user'},audio:false});
    const vid = document.getElementById('verify-vid');
    vid.srcObject = stream;
    vid.onloadedmetadata = () => { document.getElementById('vcam-overlay').classList.add('hidden'); document.getElementById('btn-capture').disabled=false; verifyLog('<span class="sl-ok">✓ Camera ready</span>'); };
  } catch(e) {
    console.error('Camera error:', e.name, e.message);
    let msg='Camera Error: '+e.message;
    if(e.name==='NotAllowedError'||e.name==='PermissionDeniedError'){msg='🔒 Permission Denied - Allow camera in browser settings';}
    else if(e.name==='NotFoundError'||e.name==='DevicesNotFoundError'){msg='📷 No camera found - Connect a webcam/USB camera';}
    else if(e.name==='NotReadableError'||e.name==='TrackStartError'){msg='⚠️ Camera in use by another app - Close it and retry';}
    else if(e.name==='SecurityError'){msg='🔐 HTTPS required or browser blocking camera access';}
    const overlay=document.getElementById('vcam-overlay');
    overlay.innerHTML='<div style="text-align:center"><div style="font-size:18px;margin-bottom:8px">'+msg+'</div><button onclick="requestCameraAccess()" style="margin-top:12px;padding:8px 16px;background:#0066cc;color:white;border:none;border-radius:6px;cursor:pointer;font-weight:600;font-size:12px">🔄 Retry Camera Access</button></div>';
    overlay.classList.remove('hidden');
    verifyLog('<span class="sl-warn">⚠ '+msg+'</span>');
  }
}'''

content = content.replace(old_func, new_func)

with open('frontend/index.html', 'w') as f:
    f.write(content)

print("✅ Camera initialization fixed with error handling and retry logic")
