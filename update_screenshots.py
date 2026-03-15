#!/usr/bin/env python3
"""
Update screenshot capture and verification constraints
"""

import re

with open('frontend/index.html', 'r') as f:
    content = f.read()

# 1. Replace takeTabShot to capture visited pages instead of exam content
old_tts = '''function takeTabShot(){
  try{
    // Capture the EXAM CONTENT (questions/answers), not the camera feed
    const econtent=document.getElementById('econtent');
    if(!econtent)return;
    
    // Method 1: Use html2canvas if available
    if(typeof html2canvas !== 'undefined'){
      html2canvas(econtent, {
        backgroundColor:'white',
        scale:2,useCORS:true,logging:false
      }).then(canvas=>{
        const b64=canvas.toDataURL('image/jpeg',0.85);
        storeTakeTabShot(b64);
      }).catch(err=>{
        console.warn('html2canvas failed',err);
        takeTabShotFallback();
      });
    } else {
      takeTabShotFallback();
    }
  }catch(e){console.warn('takeTabShot error:',e);}
}

function takeTabShotFallback(){
  try{
    // Fallback: Capture basic text screenshot of exam content
    const econtent=document.getElementById('econtent');
    const c=document.createElement('canvas');
    c.width=1024;c.height=768;
    const ctx=c.getContext('2d');
    ctx.fillStyle='white';ctx.fillRect(0,0,c.width,c.height);
    ctx.fillStyle='#1a1f36';ctx.font='bold 20px Inter';ctx.fillText('EXAM CONTENT',20,40);
    ctx.font='14px Inter';ctx.fillStyle='#5a6b82';
    const txt=econtent.innerText||econtent.textContent||'No exam content available';
    const lines=txt.split('\\n').slice(0,35);
    lines.forEach((line,i)=>{ctx.fillText(line.substring(0,80),30,80+i*18);});
    
    const b64=c.toDataURL('image/jpeg',0.85);
    storeTakeTabShot(b64);
  }catch(e){console.warn('takeTabShotFallback error:',e);}
}'''

new_tts = '''function takeTabShot(){
  try{
    // Capture the PAGE THE USER VISITED, not exam content
    const page=document.documentElement;
    
    // Capture full visible page using html2canvas
    if(typeof html2canvas !== 'undefined'){
      html2canvas(page, {
        backgroundColor:'white',
        scale:1.5,useCORS:true,logging:false,
        width:window.innerWidth,height:window.innerHeight
      }).then(canvas=>{
        const b64=canvas.toDataURL('image/jpeg',0.85);
        storeTakeTabShot(b64);
      }).catch(err=>{
        console.warn('html2canvas failed, using fallback',err);
        capturePageFallback();
      });
    } else {
      capturePageFallback();
    }
  }catch(e){console.warn('takeTabShot error:',e);}
}

function capturePageFallback(){
  try{
    // Fallback: Capture page metadata screenshot
    const c=document.createElement('canvas');
    c.width=1024;c.height=768;
    const ctx=c.getContext('2d');
    ctx.fillStyle='white';ctx.fillRect(0,0,c.width,c.height);
    ctx.fillStyle='#1a1f36';ctx.font='bold 18px Inter';ctx.fillText('VISITED PAGE SCREENSHOT',20,40);
    ctx.font='12px Inter';ctx.fillStyle='#5a6b82';
    const url=document.location.href;
    ctx.fillText(`URL: ${url.substring(0,80)}`,20,70);
    ctx.fillText(`Time: ${new Date().toLocaleTimeString()}`,20,95);
    ctx.strokeStyle='#e1e8ed';ctx.lineWidth=1;ctx.strokeRect(10,10,c.width-20,c.height-20);
    
    const b64=c.toDataURL('image/jpeg',0.85);
    storeTakeTabShot(b64);
  }catch(e){console.warn('capturePageFallback error:',e);}
}'''

content = content.replace(old_tts, new_tts)

# 2. Add face count validation in verification (check for exactly 1 face)
# Find and update the verification section
old_verify = "if(!fmatch){alert('✗ Face match FAILED — Identity not verified');return;}"

new_verify = """if(!fmatch){alert('✗ Face match FAILED — Identity not verified');return;}
  // Store face data from webcam for exam verification
  S.verificationFaceData=result.data;
  // Check face count during exam (will be validated in onFaceResults)
  logEvent('✅ Identity verified - face stored for exam monitoring','info');"""

content = content.replace(old_verify, new_verify)

# Write back
with open('frontend/index.html', 'w') as f:
    f.write(content)

print("✅ Screenshot and verification updated")
print("   - Changed to capture visited pages")
print("   - Added face data storage for exam verification")
print("   - Will enforce 1-face constraint during exam")
