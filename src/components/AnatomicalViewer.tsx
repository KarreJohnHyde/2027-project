import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { 
  Box, 
  ShieldCheck, 
  AlertTriangle, 
  CheckCircle2, 
  RotateCw, 
  Info
} from 'lucide-react';
import type { RegistrationEvaluation } from '../types/medtwin';

interface AnatomicalViewerProps {
  onEvaluateRegistration: (tauThreshold: number, simulateHighError: boolean) => Promise<RegistrationEvaluation>;
  registrationResult: RegistrationEvaluation | null;
  loadingRegistration: boolean;
}

export const AnatomicalViewer: React.FC<AnatomicalViewerProps> = ({
  onEvaluateRegistration,
  registrationResult,
  loadingRegistration,
}) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const activeObjectRef = useRef<THREE.Object3D | null>(null);
  const highlightMeshRef = useRef<THREE.Mesh | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);

  // Viewer options
  const [wireframe, setWireframe] = useState<boolean>(false);
  const [autoRotate, setAutoRotate] = useState<boolean>(true);
  const [tauThreshold, setTauThreshold] = useState<number>(5.0);
  const [simulateHighError, setSimulateHighError] = useState<boolean>(false);
  const [modelError, setModelError] = useState<string | null>(null);

  // Initialize Three.js scene
  useEffect(() => {
    const container = mountRef.current;
    if (!container) return;

    // 1. Scene
    const scene = new THREE.Scene();
    sceneRef.current = scene;

    // 2. Camera
    const camera = new THREE.PerspectiveCamera(
      45,
      container.clientWidth / container.clientHeight,
      0.1,
      1000
    );
    camera.position.set(0, 1.2, 4.5);

    // 3. Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    container.appendChild(renderer.domElement);

    // 4. Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.maxDistance = 20;
    controls.minDistance = 1;

    // 5. Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambientLight);

    const keyLight = new THREE.DirectionalLight(0x38bdf8, 2.5);
    keyLight.position.set(5, 8, 5);
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0xa855f7, 1.8);
    fillLight.position.set(-5, -3, -4);
    scene.add(fillLight);

    // 6. Highlight sphere for anatomical region (e.g. distal radius)
    const highlightGeo = new THREE.SphereGeometry(0.22, 32, 32);
    const highlightMat = new THREE.MeshStandardMaterial({
      color: 0xef4444, // Red glow
      emissive: 0x991b1b,
      roughness: 0.2,
      metalness: 0.8,
      transparent: true,
      opacity: 0.0, // Initially hidden
    });
    const highlightMesh = new THREE.Mesh(highlightGeo, highlightMat);
    highlightMesh.position.set(-0.4, -0.2, 0.5);
    scene.add(highlightMesh);
    highlightMeshRef.current = highlightMesh;

    // 7. Load GLTF Anatomical Asset
    const loader = new GLTFLoader();
    loader.load(
      '/models/Untitled.glb',
      (gltf) => {
        const model = gltf.scene;
        
        // Center and scale model
        const box = new THREE.Box3().setFromObject(model);
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        
        const maxDim = Math.max(size.x, size.y, size.z);
        const scale = maxDim > 0 ? 2.2 / maxDim : 1;
        model.scale.setScalar(scale);
        
        model.position.x = -center.x * scale;
        model.position.y = -center.y * scale;
        model.position.z = -center.z * scale;

        model.traverse((child) => {
          if ((child as THREE.Mesh).isMesh) {
            const mesh = child as THREE.Mesh;
            mesh.castShadow = true;
            mesh.receiveShadow = true;
          }
        });

        scene.add(model);
        activeObjectRef.current = model;
      },
      undefined,
      (err) => {
        console.warn('Untitled.glb failed to load; creating anatomical fallback', err);
        setModelError('Blender mesh fallback active');
        
        // Fallback reference cylinder/mesh
        const fallbackGeo = new THREE.CylinderGeometry(0.4, 0.5, 2.0, 32);
        const fallbackMat = new THREE.MeshStandardMaterial({
          color: 0x38bdf8,
          roughness: 0.3,
          metalness: 0.7,
        });
        const fallbackMesh = new THREE.Mesh(fallbackGeo, fallbackMat);
        scene.add(fallbackMesh);
        activeObjectRef.current = fallbackMesh;
      }
    );

    // 8. Resize Observer
    const handleResize = () => {
      if (!container) return;
      const width = container.clientWidth;
      const height = container.clientHeight;
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };

    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);

    // 9. Animation Loop
    let animationFrameId: number;
    let lastTime = performance.now();

    const animate = (time: number) => {
      animationFrameId = requestAnimationFrame(animate);
      const delta = (time - lastTime) * 0.001;
      lastTime = time;

      if (activeObjectRef.current && autoRotate) {
        activeObjectRef.current.rotation.y += delta * 0.4;
      }

      controls.update();
      renderer.render(scene, camera);
    };

    animationFrameId = requestAnimationFrame(animate);

    // Cleanup
    return () => {
      cancelAnimationFrame(animationFrameId);
      resizeObserver.disconnect();
      controls.dispose();
      renderer.dispose();
      highlightGeo.dispose();
      highlightMat.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [autoRotate]);

  // Update wireframe mode
  useEffect(() => {
    if (activeObjectRef.current) {
      activeObjectRef.current.traverse((child) => {
        if ((child as THREE.Mesh).isMesh) {
          const m = (child as THREE.Mesh).material;
          if (m && 'wireframe' in m) {
            (m as THREE.MeshStandardMaterial).wireframe = wireframe;
          }
        }
      });
    }
  }, [wireframe]);

  // Update region highlight based on TRE gate result
  useEffect(() => {
    if (highlightMeshRef.current) {
      const mat = highlightMeshRef.current.material as THREE.MeshStandardMaterial;
      if (registrationResult && registrationResult.is_gate_passed) {
        mat.opacity = 0.85; // Highlight anatomical region
      } else {
        mat.opacity = 0.0; // Hide region highlight on gate failure
      }
    }
  }, [registrationResult]);

  return (
    <div className="bg-slate-900/60 border border-slate-800 rounded-2xl p-5 mb-6 shadow-xl">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-800 pb-4 mb-5">
        <div>
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
              <Box size={18} />
            </div>
            <h3 className="text-sm font-bold text-white">Interactive 3D Anatomical Twin</h3>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-cyan-950 text-cyan-300 border border-cyan-800">
              Three.js • Blender .glb
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Separates Generic (L1), Finding-Associated (L2), and Patient-Specific (L3) anatomical representation.
          </p>
        </div>

        {/* 3-Level Taxonomy Indicator */}
        <div className="flex items-center gap-1.5 text-xs">
          <span className={`px-2.5 py-1 rounded-lg font-bold border ${
            !registrationResult || !registrationResult.is_gate_passed
              ? 'bg-cyan-950 text-cyan-300 border-cyan-800'
              : 'bg-slate-900 text-slate-500 border-slate-800'
          }`}>
            L1 Generic
          </span>
          <span className={`px-2.5 py-1 rounded-lg font-bold border ${
            registrationResult?.is_gate_passed
              ? 'bg-emerald-950 text-emerald-300 border-emerald-800 animate-pulse'
              : 'bg-slate-900 text-slate-500 border-slate-800'
          }`}>
            L2 Gated
          </span>
          <span className="px-2.5 py-1 rounded-lg font-bold border bg-slate-900/40 text-slate-600 border-slate-800/60" title="Reserved for future volume reconstruction">
            L3 (Reserved)
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: 3D Canvas */}
        <div className="lg:col-span-7 flex flex-col gap-3">
          <div className="relative aspect-[4/3] rounded-xl overflow-hidden bg-slate-950 border border-slate-800">
            <div ref={mountRef} className="w-full h-full cursor-grab active:cursor-grabbing" />

            {/* Viewport Floating Controls */}
            <div className="absolute top-3 left-3 flex items-center gap-2">
              <button
                type="button"
                onClick={() => setAutoRotate(!autoRotate)}
                className={`p-1.5 rounded-lg text-xs backdrop-blur-md border transition-all ${
                  autoRotate
                    ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                    : 'bg-slate-900/80 text-slate-400 border-slate-800'
                }`}
                title="Toggle Auto Rotation"
              >
                <RotateCw size={14} />
              </button>
              <button
                type="button"
                onClick={() => setWireframe(!wireframe)}
                className={`px-2 py-1 rounded-lg text-xs font-semibold backdrop-blur-md border transition-all ${
                  wireframe
                    ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40'
                    : 'bg-slate-900/80 text-slate-400 border-slate-800'
                }`}
              >
                {wireframe ? 'Solid' : 'Wireframe'}
              </button>
            </div>

            {/* Region Label Badge */}
            <div className="absolute bottom-3 left-3 right-3 flex items-center justify-between pointer-events-none">
              <div className="bg-slate-950/90 border border-slate-800 backdrop-blur-md px-3 py-1.5 rounded-lg text-xs text-slate-300">
                <span>Active Representation: </span>
                <strong className={registrationResult?.is_gate_passed ? 'text-emerald-400' : 'text-cyan-400'}>
                  {registrationResult?.is_gate_passed ? 'L2 Finding-Associated' : 'L1 Generic Reference Mesh'}
                </strong>
                {registrationResult?.assigned_region && (
                  <span className="ml-2 font-mono text-emerald-300 bg-emerald-950/80 px-1.5 py-0.5 rounded border border-emerald-800">
                    [{registrationResult.assigned_region}]
                  </span>
                )}
                {modelError && (
                  <span className="ml-2 font-mono text-amber-300 bg-amber-950/80 px-1.5 py-0.5 rounded border border-amber-800 text-[10px]">
                    ({modelError})
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Right: Registration & TRE Gate Controls */}
        <div className="lg:col-span-5 flex flex-col justify-between gap-4">
          <div>
            <div className="pb-3 border-b border-slate-800">
              <h4 className="text-sm font-bold text-white flex items-center gap-2">
                <ShieldCheck size={16} className="text-cyan-400" />
                <span>Held-Out TRE Registration Gate (Eqs. 11–12)</span>
              </h4>
              <p className="text-xs text-slate-400 mt-1">
                A region is drawn only if Arun SVD fit succeeds and held-out TRE does not exceed τ_TRE.
              </p>
            </div>

            {/* Simulation controls */}
            <div className="mt-4 space-y-4">
              <div>
                <div className="flex justify-between text-xs text-slate-400 mb-1">
                  <span>Registration Gate Threshold (τ_TRE)</span>
                  <span className="font-mono text-cyan-400 font-bold">{tauThreshold.toFixed(1)} mm</span>
                </div>
                <input
                  type="range"
                  min="2.0"
                  max="10.0"
                  step="0.5"
                  value={tauThreshold}
                  onChange={(e) => setTauThreshold(parseFloat(e.target.value))}
                  className="w-full accent-cyan-500 cursor-pointer"
                />
              </div>

              <div className="flex items-center justify-between p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs">
                <div>
                  <span className="font-semibold text-slate-300">Simulate High-Error Scan</span>
                  <p className="text-[11px] text-slate-500">Injects registration error &gt; τ_TRE</p>
                </div>
                <button
                  type="button"
                  onClick={() => setSimulateHighError(!simulateHighError)}
                  className={`px-3 py-1.5 rounded-lg font-semibold transition-all ${
                    simulateHighError
                      ? 'bg-rose-600 text-white shadow-md shadow-rose-600/30'
                      : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                  }`}
                >
                  {simulateHighError ? 'High Error Active' : 'Normal Error'}
                </button>
              </div>

              <button
                type="button"
                disabled={loadingRegistration}
                onClick={() => onEvaluateRegistration(tauThreshold, simulateHighError)}
                className="w-full py-2.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold shadow-md shadow-cyan-600/20 transition-all disabled:opacity-50"
              >
                {loadingRegistration ? 'Evaluating Arun SVD & TRE...' : 'Evaluate Registration Gate'}
              </button>

              {/* Gate Result Display */}
              {registrationResult && (
                <div className={`p-4 rounded-xl border ${
                  registrationResult.is_gate_passed
                    ? 'bg-emerald-950/30 border-emerald-800 text-emerald-300'
                    : 'bg-rose-950/30 border-rose-800 text-rose-300'
                } text-xs space-y-2`}>
                  <div className="flex items-center justify-between font-bold">
                    <span className="flex items-center gap-1.5">
                      {registrationResult.is_gate_passed ? <CheckCircle2 size={15} /> : <AlertTriangle size={15} />}
                      <span>{registrationResult.is_gate_passed ? 'GATE PASSED: L2 ENABLED' : 'GATE FAILED: L1 FALLBACK'}</span>
                    </span>
                    <span className="font-mono">TRE: {registrationResult.held_out_tre?.toFixed(2)} mm</span>
                  </div>

                  <p className="text-[11px] text-slate-300 leading-relaxed">
                    {registrationResult.message}
                  </p>

                  <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800/80 text-[11px] text-slate-400 font-mono">
                    <div>Fit RMS: {registrationResult.fitting_error_rms?.toFixed(2)} mm</div>
                    <div>Held-out Q count: {registrationResult.held_out_count}</div>
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="p-3 rounded-xl bg-slate-950 border border-slate-800 text-[11px] text-slate-400 flex items-start gap-2">
            <Info size={14} className="text-cyan-400 shrink-0 mt-0.5" />
            <span>
              <strong>L3 Policy:</strong> Generic mesh gives no patient-specific correspondence. Patient-specific
              reconstruction requires calibrated 3D volumetric segmentation and non-rigid registration (IEEE Section III).
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
