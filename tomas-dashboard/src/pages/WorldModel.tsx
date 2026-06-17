import { useEffect, useRef } from 'react';
import * as THREE from 'three';

const CONCEPTS = ['量子纠缠','贝尔不等式','波函数','薛定谔方程','自旋','量子隧穿','EPR','退相干','叠加态','量子门','哈密顿量','态矢量','量子场','规范对称','虚时间','量子泡沫','普朗克常量','不确定性','纠缠熵','量子比特'];

const DIKWP_COLORS = ['#3b82f6','#06b6d4','#10b981','#f59e0b','#8b5cf6','#4a5568'];

export default function WorldModel() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;

    // Scene
    const scene = new THREE.Scene();
    scene.background = new THREE.Color('#0a0e1a');

    const camera = new THREE.PerspectiveCamera(60, el.clientWidth / el.clientHeight, 0.1, 100);
    camera.position.z = 12;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(el.clientWidth, el.clientHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);

    // Stars
    const starGeo = new THREE.BufferGeometry();
    const starCount = 400;
    const starVerts = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount * 3; i += 3) {
      starVerts[i] = (Math.random() - 0.5) * 30;
      starVerts[i + 1] = (Math.random() - 0.5) * 30;
      starVerts[i + 2] = (Math.random() - 0.5) * 20;
    }
    starGeo.setAttribute('position', new THREE.BufferAttribute(starVerts, 3));
    const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0x64748b, size: 0.03 }));
    scene.add(stars);

    // Nodes
    const nodes: THREE.Mesh[] = [];
    nodes.forEach((n) => {}); // placeholder
    for (let i = 0; i < CONCEPTS.length; i++) {
      const layer = i < 4 ? 0 : i < 8 ? 1 : i < 14 ? 2 : i < 17 ? 3 : i < 19 ? 4 : 5;
      const color = DIKWP_COLORS[layer];
      const isDz = layer === 5;
      const r = isDz ? 0.25 : 0.3 + Math.random() * 0.35;

      const geo = new THREE.SphereGeometry(r, 32, 32);
      const mat = new THREE.MeshPhongMaterial({
        color: new THREE.Color(color),
        emissive: new THREE.Color(color).multiplyScalar(isDz ? 0.1 : 0.3),
        transparent: true,
        opacity: isDz ? 0.4 : 0.85,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set((Math.random() - 0.5) * 8, (Math.random() - 0.5) * 6, (Math.random() - 0.5) * 4);
      mesh.userData = { label: CONCEPTS[i], layer };
      scene.add(mesh);
      nodes.push(mesh);
    }

    // Edges
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const d = nodes[i].position.distanceTo(nodes[j].position);
        if (d < 3.5) {
          const pts = [nodes[i].position, nodes[j].position];
          const edgeGeo = new THREE.BufferGeometry().setFromPoints(pts);
          const edge = new THREE.Line(edgeGeo, new THREE.LineBasicMaterial({ color: 0x1e2d4a, transparent: true, opacity: 0.4 }));
          scene.add(edge);
        }
      }
    }

    // Lights
    scene.add(new THREE.AmbientLight(0x334155, 0.6));
    const dirLight = new THREE.DirectionalLight(0x3b82f6, 0.5);
    dirLight.position.set(5, 5, 5);
    scene.add(dirLight);

    // Animation
    let animationId: number;
    const animate = () => {
      animationId = requestAnimationFrame(animate);
      stars.rotation.y += 0.0001;
      nodes.forEach((n, i) => {
        n.rotation.y += 0.003;
        n.position.y += Math.sin(Date.now() * 0.0005 + i) * 0.003;
      });
      renderer.render(scene, camera);
    };
    animate();

    // Mouse rotate
    let isDragging = false;
    let prevX = 0, prevY = 0;
    const onDown = (e: MouseEvent) => { isDragging = true; prevX = e.clientX; prevY = e.clientY; };
    const onMove = (e: MouseEvent) => {
      if (!isDragging) return;
      const dx = e.clientX - prevX;
      const dy = e.clientY - prevY;
      camera.position.x -= dx * 0.01;
      camera.position.y += dy * 0.01;
      camera.lookAt(0, 0, 0);
      prevX = e.clientX; prevY = e.clientY;
    };
    const onUp = () => { isDragging = false; };

    el.addEventListener('mousedown', onDown);
    el.addEventListener('mousemove', onMove);
    el.addEventListener('mouseup', onUp);
    el.addEventListener('mouseleave', onUp);

    const onResize = () => {
      camera.aspect = el.clientWidth / el.clientHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(el.clientWidth, el.clientHeight);
    };
    window.addEventListener('resize', onResize);

    return () => {
      cancelAnimationFrame(animationId);
      renderer.dispose();
      el.removeChild(renderer.domElement);
      window.removeEventListener('resize', onResize);
    };
  }, []);

  return (
    <div ref={containerRef} className="w-full rounded-xl overflow-hidden border" style={{ height: 'calc(100vh - var(--header-h) - 120px)', borderColor: 'var(--border)' }}>
      <div className="absolute bottom-4 left-4 z-10 flex gap-2">
        {[
          { label: 'D', color: '#3b82f6' },
          { label: 'I', color: '#06b6d4' },
          { label: 'K', color: '#10b981' },
          { label: 'W', color: '#f59e0b' },
          { label: 'P', color: '#8b5cf6' },
          { label: 'DZ', color: '#4a5568' },
        ].map((item) => (
          <span key={item.label} className="badge text-xs" style={{ border: `1px solid ${item.color}`, color: item.color }}>
            {item.label}
          </span>
        ))}
      </div>
    </div>
  );
}
