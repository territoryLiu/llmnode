import React from 'react';

export function Background() {
  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none z-[-1]">
      <div className="noise-overlay"></div>
      {/* Diffuse Orbs */}
      <div className="absolute top-[-10%] left-[-10%] w-[50vw] h-[50vw] bg-diffuse-orange/40 rounded-full blur-[100px] animate-float"></div>
      <div className="absolute bottom-[-20%] right-[-10%] w-[60vw] h-[60vw] bg-diffuse-mint/30 rounded-full blur-[120px] animate-float-delayed"></div>
      <div className="absolute top-[20%] right-[10%] w-[35vw] h-[35vw] bg-diffuse-pink/30 rounded-full blur-[90px] animate-float-slow"></div>
    </div>
  );
}
