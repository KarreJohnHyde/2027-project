import { Clone, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import React, { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import { Box, Check, LoaderCircle, TriangleAlert } from "lucide-react";

type AnatomyOption = {
  id: "heart" | "respiratory" | "brain" | "digestive";
  label: string;
  system: string;
  url: string;
  license: string;
};

const ANATOMY_OPTIONS: AnatomyOption[] = [
  { id: "heart", label: "Heart", system: "Cardiovascular", url: "/models/medtwin_l1_heart.glb", license: "CC BY-SA 4.0" },
  { id: "respiratory", label: "Lungs", system: "Respiratory / Endocrine", url: "/models/medtwin_l1_respiratory.glb", license: "CC BY-SA 4.0" },
  { id: "brain", label: "Brain", system: "Nervous", url: "/models/medtwin_l1_brain.glb", license: "CC BY-SA 3.0 / 4.0 adaptations" },
  { id: "digestive", label: "GI", system: "Gastrointestinal", url: "/models/medtwin_l1_digestive.glb", license: "CC BY-SA 4.0" },
];

type AssetState =
  | { status: "loading"; meshCount: 0; assetId: AnatomyOption["id"] }
  | { status: "loaded"; meshCount: number; assetId: AnatomyOption["id"] }
  | { status: "error"; meshCount: 0; assetId: AnatomyOption["id"] };

class ModelErrorBoundary extends React.Component<
  { children: React.ReactNode; onError: () => void; resetKey: AnatomyOption["id"] },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    this.props.onError();
  }

  componentDidUpdate(previousProps: Readonly<{ resetKey: AnatomyOption["id"] }>) {
    if (this.state.failed && previousProps.resetKey !== this.props.resetKey) {
      this.setState({ failed: false });
    }
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

function ReferenceModel({ option, onLoaded }: { option: AnatomyOption; onLoaded: (assetId: AnatomyOption["id"], meshCount: number) => void }) {
  const gltf = useGLTF(option.url, false, true);

  const normalized = useMemo(() => {
    gltf.scene.updateMatrixWorld(true);
    let meshCount = 0;
    gltf.scene.traverse((object) => {
      if ((object as THREE.Mesh).isMesh) meshCount += 1;
    });

    const bounds = new THREE.Box3().setFromObject(gltf.scene);
    const size = bounds.getSize(new THREE.Vector3());
    const center = bounds.getCenter(new THREE.Vector3());
    const maxDimension = Math.max(size.x, size.y, size.z);
    if (meshCount < 1 || bounds.isEmpty() || !Number.isFinite(maxDimension) || maxDimension <= 0) {
      throw new Error("The GLB contains no finite renderable bounds.");
    }

    const scale = 2.2 / maxDimension;
    return {
      meshCount,
      position: [-center.x * scale, -center.y * scale, -center.z * scale] as [number, number, number],
      scale,
    };
  }, [gltf.scene]);

  useEffect(() => {
    onLoaded(option.id, normalized.meshCount);
  }, [normalized.meshCount, onLoaded, option.id]);

  return (
    <group position={normalized.position} scale={normalized.scale}>
      <Clone object={gltf.scene} />
    </group>
  );
}

function Scene({ option, onLoaded }: { option: AnatomyOption; onLoaded: (assetId: AnatomyOption["id"], meshCount: number) => void }) {
  return (
    <>
      <color attach="background" args={["#071923"]} />
      <ambientLight intensity={1.8} />
      <directionalLight position={[4, 6, 5]} intensity={3.2} color="#d9ffff" />
      <directionalLight position={[-4, 1, -3]} intensity={2.1} color="#ff9a78" />
      <Suspense fallback={null}>
        <ReferenceModel option={option} onLoaded={onLoaded} />
      </Suspense>
      <OrbitControls makeDefault enablePan={false} autoRotate autoRotateSpeed={0.55} />
    </>
  );
}

export default function DigitalTwin3D({
  activeSystem,
  compact = false,
}: {
  activeSystem?: string;
  compact?: boolean;
}) {
  const [selectedId, setSelectedId] = useState<AnatomyOption["id"]>(() => {
    const hint = activeSystem?.toLowerCase() ?? "";
    return (ANATOMY_OPTIONS.find((option) => hint.includes(option.id) || hint.includes(option.system.toLowerCase())) ?? ANATOMY_OPTIONS[0]).id;
  });
  const selected = ANATOMY_OPTIONS.find((option) => option.id === selectedId) ?? ANATOMY_OPTIONS[0];
  const [asset, setAsset] = useState<AssetState>({ status: "loading", meshCount: 0, assetId: selected.id });

  const handleLoaded = useCallback((assetId: AnatomyOption["id"], meshCount: number) => {
    setAsset((current) => current.assetId === assetId ? { status: "loaded", meshCount, assetId } : current);
  }, [setAsset]);

  function selectAsset(option: AnatomyOption) {
    setSelectedId(option.id);
    setAsset({ status: "loading", meshCount: 0, assetId: option.id });
  }

  return (
    <div className={`digital-twin ${compact ? "digital-twin-compact" : ""}`}>
      {!compact && (
        <div className="twin-modebar">
          <div className="view-modes" role="tablist" aria-label="Generic anatomical references">
            {ANATOMY_OPTIONS.map((option) => (
              <button
                key={option.id}
                type="button"
                role="tab"
                aria-selected={selected.id === option.id}
                className={selected.id === option.id ? "active" : ""}
                onClick={() => selectAsset(option)}
              >
                <Box size={12} /> {option.label}
              </button>
            ))}
          </div>
          <span>L1 ONLY · {selected.system.toUpperCase()}</span>
        </div>
      )}
      <div
        className="twin-canvas"
        data-model-id={selected.id}
        data-model-status={asset.status}
        aria-label={`Interactive generic Level 1 ${selected.label} GLB reference`}
      >
        <ModelErrorBoundary resetKey={selected.id} onError={() => setAsset({ status: "error", meshCount: 0, assetId: selected.id })}>
          <Canvas camera={{ position: [0, 0.25, 4.5], fov: 42 }} dpr={[1, 1.75]}>
            <Scene option={selected} onLoaded={handleLoaded} />
          </Canvas>
        </ModelErrorBoundary>
        {asset.status === "error" && (
          <div className="model-error"><TriangleAlert size={18} /> {selected.label} GLB could not be rendered.</div>
        )}
        <div className={`canvas-status model-${asset.status}`}>
          {asset.status === "loaded" ? <Check size={12} /> : asset.status === "error" ? <TriangleAlert size={12} /> : <LoaderCircle size={12} />}
          <b>{asset.status === "loaded" ? "GLB LOADED" : asset.status.toUpperCase()}</b>
          {asset.status === "loaded" ? `${asset.meshCount} mesh${asset.meshCount === 1 ? "" : "es"}` : selected.label}
        </div>
      </div>
      {!compact && (
        <div className="forecast-controls">
          <p>
            {selected.license} generic reference · upstream audit pending · no patient registration.
            {" "}<a href="/models/ATTRIBUTION.md" target="_blank" rel="noreferrer">Attribution</a>
          </p>
        </div>
      )}
    </div>
  );
}
