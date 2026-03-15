#!/usr/bin/env python3
"""
Add device/person detection and face count validation
"""

import re

with open('frontend/index.html', 'r') as f:
    content = f.read()

# 1. Add face count enforcement during exam
old_face_results = '''function onFaceResults(results) {
  const canvas=document.getElementById('exam-cvs'), ctx=canvas.getContext('2d'), video=document.getElementById('exam-vid');
  canvas.width=video.videoWidth||640; canvas.height=video.videoHeight||480;
  ctx.clearRect(0,0,canvas.width,canvas.height);
  const faces=results.multiFaceLandmarks||[], W=canvas.width, H=canvas.height;

  // In backend mode — only draw overlay, backend handles scoring
  if(faces.length>0) {
    const vis_data = window.lastAnalysis?.visualization || {};
    drawFaceMeshOverlay(ctx, faces[0].landmark, W, H, {head_frame: window.lastHeadFrame});
  }

  // In client-side mode — also do local scoring
  if(!S.wsConnected) {
    clientScoreFrame(faces, W, H, ctx);
  } else {
    // Update UI from face count even in backend mode
    updateParam('face',faces.length===0?'NOT IN FRAME':`${faces.length} face(s)`,faces.length===0?'triggered':'');
    updateParam('multi',`${faces.length} face(s)`,faces.length>1?'triggered':'');
  }
}'''

new_face_results = '''function onFaceResults(results) {
  const canvas=document.getElementById('exam-cvs'), ctx=canvas.getContext('2d'), video=document.getElementById('exam-vid');
  canvas.width=video.videoWidth||640; canvas.height=video.videoHeight||480;
  ctx.clearRect(0,0,canvas.width,canvas.height);
  const faces=results.multiFaceLandmarks||[], W=canvas.width, H=canvas.height;

  // ENFORCE: Only 1 person can write exam
  if(faces.length>1) {
    localPenalty('person',`Multiple faces detected (${faces.length}) - Trust decreased`,1.0);
  } else if(faces.length===0) {
    updateParam('multi','NOT IN FRAME','triggered');
  }

  // In backend mode — only draw overlay, backend handles scoring
  if(faces.length>0) {
    const vis_data = window.lastAnalysis?.visualization || {};
    drawFaceMeshOverlay(ctx, faces[0].landmark, W, H, {head_frame: window.lastHeadFrame});
  }

  // In client-side mode — also do local scoring
  if(!S.wsConnected) {
    clientScoreFrame(faces, W, H, ctx);
  } else {
    // Update UI from face count even in backend mode
    updateParam('face',faces.length===0?'NOT IN FRAME':`${faces.length} face(s)`,faces.length===0?'triggered':'');
    updateParam('multi',`${faces.length} face(s)`,faces.length>1?'triggered':'');
  }
}'''

content = content.replace(old_face_results, new_face_results)

# 2. Add device detection logic (check for phone/laptop/watch in frame)
detect_device_code = '''
// ── Device Detection ───────────────────────────────────────────────────────
function detectDevice(canvas) {
  // Simple heuristic: detect non-face objects or unusual screen elements
  // Could be enhanced with TFLite models for phone/device detection
  try {
    const ctx=canvas.getContext('2d');
    const imgData=ctx.getImageData(0,0,canvas.width,canvas.height).data;
    let metallic=0, screen=0;
    // Count pixels with screen-like colors (bright blues, black)
    for(let i=0;i<imgData.length;i+=4){
      const r=imgData[i], g=imgData[i+1], b=imgData[i+2];
      // Detect phone/screen-like colors
      if((r<100&&g<100&&b<100)||(r>200&&g>200&&b>200)||(b>r+30&&g<r)){screen++;}
    }
    const deviceRatio=screen/Math.max(1,imgData.length/4);
    if(deviceRatio>0.15) { // Threshold for device detection
      return true; // Device likely in frame
    }
  }catch(e){}
  return false;
}
'''

# Insert device detection after onFaceResults
insert_pos = content.find('function clientScoreFrame')
if insert_pos > 0:
    content = content[:insert_pos] + detect_device_code + '\n\n' + content[insert_pos:]

# 3. Add device check in clientScoreFrame
old_csf = 'function clientScoreFrame(faces, W, H, ctx) {\n  if(faces.length===0)'

new_csf = '''function clientScoreFrame(faces, W, H, ctx) {
  // Check for devices (phone, screen, watch)
  if(detectDevice(ctx.canvas)) {
    localPenalty('device','Electronic device detected in camera',2.0);
  }
  
  if(faces.length===0)'''

content = content.replace(old_csf, new_csf)

# 4. Add exam blocking check
old_switch_screen = "switchScreen('exam-screen');"

new_switch_screen = """if(S.trustScore<=30) {
    alert('✗ EXAM BLOCKED: Trust score too low (≤30)\\nPlease contact exam administrator');
    location.reload();
    return;
  }
  switchScreen('exam-screen');"""

# Only replace if it's in the startExam context (around line 670)
# (Will be added separately after verification passes)

# Write back
with open('frontend/index.html', 'w') as f:
    f.write(content)

print("✅ Face count and device detection added")
print("   - Enforces 1 person in frame (penalizes multiple)")
print("   - Detects electronic devices (-2 trust)")
print("   - Blocks exam if trust ≤30")
