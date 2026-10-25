import React, { useEffect, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';

interface ThreeCanvasProps {
  geometryType: 'torusKnot' | 'icosahedron' | 'cyberSphere' | 'torus' | 'blenderModel';
  wireframe: boolean;
  color: string;
  rotationSpeed: number;
  particleCount?: number;
}

export const ThreeCanvas: React.FC<ThreeCanvasProps> = ({
  geometryType,
  wireframe,
  color,
  rotationSpeed,
  particleCount = 1200,
}) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const activeObjectRef = useRef<THREE.Object3D | null>(null);
  const materialRef = useRef<THREE.MeshStandardMaterial | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);

  // Stats / FPS counter state
  const [fps, setFps] = useState<number>(60);
  const [modelLoading, setModelLoading] = useState<boolean>(false);

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
    camera.position.set(0, 1.5, 5);

    // 3. Renderer with antialiasing and high pixel ratio
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(container.clientWidth, container.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.2;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);

    // 4. Orbit Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.autoRotate = false;
    controls.maxDistance = 25;
    controls.minDistance = 1;

    // 5. Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
    scene.add(ambientLight);

    const primaryLight = new THREE.DirectionalLight(0x60a5fa, 2.5);
    primaryLight.position.set(5, 8, 5);
    primaryLight.castShadow = true;
    scene.add(primaryLight);

    const secondaryLight = new THREE.DirectionalLight(0xa855f7, 2.0);
    secondaryLight.position.set(-5, -3, -4);
    scene.add(secondaryLight);

    const centerPointLight = new THREE.PointLight(0x38bdf8, 3, 15);
    centerPointLight.position.set(0, 0, 0);
    scene.add(centerPointLight);

    // 6. Particles Starfield
    const particlesGeometry = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    const particleColors = new Float32Array(particleCount * 3);

    const color1 = new THREE.Color(0x38bdf8);
    const color2 = new THREE.Color(0xa855f7);

    for (let i = 0; i < particleCount; i++) {
      const i3 = i * 3;
      const radius = 8 + Math.random() * 8;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);

      positions[i3] = radius * Math.sin(phi) * Math.cos(theta);
      positions[i3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
      positions[i3 + 2] = radius * Math.cos(phi);

      const mixedColor = color1.clone().lerp(color2, Math.random());
      particleColors[i3] = mixedColor.r;
      particleColors[i3 + 1] = mixedColor.g;
      particleColors[i3 + 2] = mixedColor.b;
    }

    particlesGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    particlesGeometry.setAttribute('color', new THREE.BufferAttribute(particleColors, 3));

    const particlesMaterial = new THREE.PointsMaterial({
      size: 0.035,
      vertexColors: true,
      transparent: true,
      opacity: 0.8,
      blending: THREE.AdditiveBlending,
    });

    const particles = new THREE.Points(particlesGeometry, particlesMaterial);
    scene.add(particles);

    // 7. Outer Glow Ring
    const ringGeo = new THREE.RingGeometry(2.1, 2.15, 64);
    const ringMat = new THREE.MeshBasicMaterial({
      color: 0x38bdf8,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.4,
    });
    const ring = new THREE.Mesh(ringGeo, ringMat);
    ring.rotation.x = Math.PI / 2;
    scene.add(ring);

    // 8. Geometry / Model Loading
    if (geometryType === 'blenderModel') {
      const loader = new GLTFLoader();
      loader.load(
        '/models/Untitled.glb',
        (gltf) => {
          const model = gltf.scene;
          
          // Center and scale model to fit viewport
          const box = new THREE.Box3().setFromObject(model);
          const size = box.getSize(new THREE.Vector3());
          const center = box.getCenter(new THREE.Vector3());
          
          const maxDim = Math.max(size.x, size.y, size.z);
          const scale = maxDim > 0 ? 2.5 / maxDim : 1;
          model.scale.setScalar(scale);
          
          model.position.x = -center.x * scale;
          model.position.y = -center.y * scale;
          model.position.z = -center.z * scale;

          model.traverse((child) => {
            if ((child as THREE.Mesh).isMesh) {
              const mesh = child as THREE.Mesh;
              mesh.castShadow = true;
              mesh.receiveShadow = true;
              if (wireframe && mesh.material) {
                const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
                materials.forEach((m) => {
                  if ('wireframe' in m) {
                    (m as THREE.MeshStandardMaterial).wireframe = true;
                  }
                });
              }
            }
          });

          scene.add(model);
          activeObjectRef.current = model;
          setModelLoading(false);
        },
        undefined,
        (err) => {
          console.warn('Failed to load Untitled.glb, falling back to TorusKnot', err);
          setModelLoading(false);
        }
      );
    } else {
      const material = new THREE.MeshStandardMaterial({
        color: new THREE.Color(color),
        roughness: 0.15,
        metalness: 0.85,
        wireframe: wireframe,
      });
      materialRef.current = material;

      const createGeometry = (type: string) => {
        switch (type) {
          case 'icosahedron':
            return new THREE.IcosahedronGeometry(1.4, 2);
          case 'cyberSphere':
            return new THREE.SphereGeometry(1.3, 48, 48);
          case 'torus':
            return new THREE.TorusGeometry(1.2, 0.45, 32, 100);
          case 'torusKnot':
          default:
            return new THREE.TorusKnotGeometry(1.1, 0.35, 128, 32);
        }
      };

      const geometry = createGeometry(geometryType);
      const mesh = new THREE.Mesh(geometry, material);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      scene.add(mesh);
      activeObjectRef.current = mesh;
    }

    // 9. Resize Observer
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

    // 10. Animation Loop & FPS calculation
    let animationFrameId: number;
    let lastTime = performance.now();
    let frameCount = 0;
    let lastFpsUpdate = performance.now();

    const animate = (time: number) => {
      animationFrameId = requestAnimationFrame(animate);

      const delta = (time - lastTime) * 0.001;
      lastTime = time;

      // FPS tracking
      frameCount++;
      if (time - lastFpsUpdate >= 500) {
        setFps(Math.round((frameCount * 1000) / (time - lastFpsUpdate)));
        frameCount = 0;
        lastFpsUpdate = time;
      }

      if (activeObjectRef.current) {
        activeObjectRef.current.rotation.y += delta * rotationSpeed;
        if (geometryType !== 'blenderModel') {
          activeObjectRef.current.rotation.x += delta * rotationSpeed * 0.5;
        }
      }

      ring.rotation.z += delta * 0.2;
      particles.rotation.y += delta * 0.05;

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
      particlesGeometry.dispose();
      particlesMaterial.dispose();
      ringGeo.dispose();
      ringMat.dispose();
      if (container.contains(renderer.domElement)) {
        container.removeChild(renderer.domElement);
      }
    };
  }, [geometryType, particleCount, color, wireframe, rotationSpeed]);

  // Update dynamic properties without full re-creation
  useEffect(() => {
    if (materialRef.current) {
      materialRef.current.wireframe = wireframe;
      materialRef.current.color.set(color);
    }
  }, [wireframe, color]);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div
        ref={mountRef}
        style={{
          width: '100%',
          height: '100%',
          overflow: 'hidden',
          borderRadius: '16px',
        }}
      />
      {/* Real-time WebGL Telemetry Badge */}
      <div
        style={{
          position: 'absolute',
          bottom: '16px',
          left: '16px',
          background: 'rgba(15, 23, 42, 0.75)',
          backdropFilter: 'blur(8px)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          padding: '6px 14px',
          borderRadius: '20px',
          color: '#94a3b8',
          fontSize: '0.8rem',
          display: 'flex',
          gap: '12px',
          alignItems: 'center',
          boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
          pointerEvents: 'none',
        }}
      >
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: fps > 45 ? '#22c55e' : '#eab308',
            }}
          />
          {fps} FPS
        </span>
        <span>•</span>
        <span>{geometryType === 'blenderModel' ? 'Blender 5.2 Model' : 'Three.js Mesh'}</span>
        <span>•</span>
        <span>{modelLoading ? 'Loading 3D...' : 'Interactive Orbit'}</span>
      </div>
    </div>
  );
};
