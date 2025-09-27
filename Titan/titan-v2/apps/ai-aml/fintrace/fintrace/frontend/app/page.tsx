"use client"

import { useState, useEffect, useRef } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card"
import { Button } from "../components/ui/button"
import { Badge } from "../components/ui/badge"
import {
  ChevronDown,
  Shield,
  Brain,
  Network,
  FileText,
  Users,
  Target,
  Zap,
  Eye,
  TrendingUp,
  Database,
  Cpu,
  Bot,
} from "lucide-react"

export default function HackVerseBlog() {
  const [scrollY, setScrollY] = useState(0)
  const [activeSection, setActiveSection] = useState("hero")
  const sectionRefs = useRef<{ [key: string]: HTMLElement | null }>({})

  useEffect(() => {
    const handleScroll = () => setScrollY(window.scrollY)
    window.addEventListener("scroll", handleScroll)
    return () => window.removeEventListener("scroll", handleScroll)
  }, [])

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("animate-subtle-in")
            entry.target.classList.remove("animate-subtle-out")
          } else {
            entry.target.classList.add("animate-subtle-out")
            entry.target.classList.remove("animate-subtle-in")
          }
        })
      },
      {
        threshold: 0.3,
        rootMargin: "0px 0px -20% 0px",
      },
    )

    // Observe all sections
    Object.values(sectionRefs.current).forEach((ref) => {
      if (ref) observer.observe(ref)
    })

    return () => observer.disconnect()
  }, [])

  const scrollToSection = (sectionId: string) => {
    const element = document.getElementById(sectionId)
    if (element) {
      element.scrollIntoView({
        behavior: "smooth",
        block: "start",
      })
    }
  }

  const setSectionRef = (id: string) => (el: HTMLElement | null) => {
    sectionRefs.current[id] = el
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <nav className="fixed top-0 w-full bg-background/95 backdrop-blur-sm border-b border-secondary/20 z-50 transition-all duration-300">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="relative">
                <Shield className="h-10 w-10 text-secondary" />
              </div>
              <div>
                <span className="text-2xl font-bold text-secondary">FinTrace</span>
                <p className="text-xs text-muted-foreground">AML Intelligence</p>
              </div>
            </div>
            <div className="hidden md:flex space-x-8">
              {[
                { name: "Overview", id: "overview" },
                { name: "Problem", id: "problem" },
                { name: "Solution", id: "solution" },
                { name: "Architecture", id: "architecture" },
                { name: "Impact", id: "impact" },
              ].map((item) => (
                <button
                  key={item.name}
                  onClick={() => scrollToSection(item.id)}
                  className="relative text-muted-foreground hover:text-secondary transition-colors duration-300 group"
                >
                  {item.name}
                  <div className="absolute -bottom-1 left-0 w-0 h-0.5 bg-secondary transition-all duration-300 group-hover:w-full" />
                </button>
              ))}
            </div>
          </div>
        </div>
      </nav>

      <section id="hero" className="relative min-h-screen flex items-center justify-center overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-secondary/10 via-background to-accent/5" />

        <div className="absolute inset-0">
          {[...Array(20)].map((_, i) => (
            <div
              key={i}
              className="absolute w-1 h-1 bg-secondary/20 rounded-full animate-pulse"
              style={{
                left: `${Math.random() * 100}%`,
                top: `${Math.random() * 100}%`,
                animationDelay: `${Math.random() * 2}s`,
                animationDuration: `${2 + Math.random()}s`,
              }}
            />
          ))}
        </div>

        <div className="relative z-10 text-center max-w-6xl mx-auto px-6">
          <div className="animate-fade-in-up">
            <Badge className="mb-8 bg-secondary/20 text-secondary border-secondary/40 hover:bg-secondary/30 transition-all duration-300 text-lg px-6 py-2">
              HackVerse 2025 • 28th-30th August
            </Badge>
          </div>

          <h1
            className="text-6xl md:text-8xl font-bold mb-8 text-balance animate-fade-in-up"
            style={{ animationDelay: "0.2s" }}
          >
            <span className="text-primary">AI-Based</span> <span className="text-secondary">Solution Engineering</span>{" "}
            <span className="text-primary">HackVerse 2025</span>
          </h1>

          <div className="mb-12 animate-fade-in-up" style={{ animationDelay: "0.4s" }}>
            <h2 className="text-3xl md:text-4xl font-semibold mb-4 text-secondary">Presenting FinTrace</h2>
            <p className="text-xl md:text-2xl text-muted-foreground text-pretty max-w-4xl mx-auto">
              Revolutionary GAN-Powered AML Intelligence System that detects money laundering networks with
              unprecedented accuracy
            </p>
          </div>

          <div
            className="flex flex-col sm:flex-row gap-6 justify-center animate-fade-in-up"
            style={{ animationDelay: "0.6s" }}
          >
            <Button
              size="lg"
              onClick={() => scrollToSection("overview")}
              className="bg-secondary hover:bg-secondary/90 text-secondary-foreground transition-all duration-300 hover:scale-105 text-lg px-8 py-4"
            >
              Explore Solution <ChevronDown className="ml-2 h-5 w-5" />
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="border-secondary/50 text-secondary hover:bg-secondary hover:text-secondary-foreground bg-transparent transition-all duration-300 hover:scale-105 text-lg px-8 py-4"
            >
              View Architecture
            </Button>
          </div>
        </div>
      </section>

      <section
        ref={setSectionRef("team")}
        className="py-24 bg-card/30 border-y border-secondary/10 section-animate opacity-0 translate-y-5"
      >
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-16 animate-fade-in-up stagger-animate">
            <h2 className="text-4xl md:text-5xl font-bold mb-6 text-secondary">Team Excellence</h2>
            <p className="text-xl text-muted-foreground max-w-3xl mx-auto">
              Three passionate developers from PES University Bangalore, united by innovation
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8 mb-16">
            {[
              {
                name: "ARYAN D HARITSA",
                usn: "PES1UG22CS114",
                phone: "+91 7483723182",
                role: "Data/ML Engineer",
                photo:
                  "https://hebbkx1anhila5yf.public.blob.vercel-storage.com/WhatsApp%20Image%202025-08-17%20at%207.05.03%20PM-2Cn6piQugd5ukhgXwz2i6uk3UXnCQH.jpeg",
              },
              {
                name: "NANDAN HEMARAJU",
                usn: "PES2UG22CS335",
                phone: "+91 8618537382",
                role: "Frontend Developer",
                photo:
                  "https://hebbkx1anhila5yf.public.blob.vercel-storage.com/WhatsApp%20Image%202025-08-17%20at%207.06.15%20PM-Wl1xTbO9Rx03lFV45p5HnrEndXYqcv.jpeg",
              },
              {
                name: "BHAVYA BAFNA",
                usn: "PES1UG22CS142",
                phone: "+91 9535477969",
                role: "Backend Developer",
                photo:
                  "https://hebbkx1anhila5yf.public.blob.vercel-storage.com/WhatsApp%20Image%202025-08-17%20at%207.07.45%20PM-CETrusERyRVSfwowMI2EXw55WQu6Qp.jpeg",
              },
            ].map((member, index) => (
              <Card
                key={index}
                className="text-center interactive-hover transition-all duration-700 hover:border-secondary/50 animate-fade-in-up group bg-card/50 backdrop-blur-sm stagger-animate animate-glow-pulse"
                style={{ animationDelay: `${index * 0.2}s` }}
              >
                <CardHeader className="pb-4">
                  <div className="relative mx-auto mb-6">
                    <div className="w-32 h-32 rounded-full overflow-hidden group-hover:scale-110 transition-all duration-500 animate-float border-4 border-secondary/30 group-hover:border-secondary/60">
                      <img
                        src={member.photo || "/placeholder.svg"}
                        alt={member.name}
                        className="w-full h-full object-cover"
                      />
                    </div>
                    <div className="absolute inset-0 bg-secondary/10 rounded-full blur-xl group-hover:blur-2xl transition-all duration-500" />
                  </div>
                  <CardTitle className="text-xl group-hover:text-secondary transition-colors duration-500">
                    {member.name}
                  </CardTitle>
                  <CardDescription className="text-secondary/80 font-medium">{member.role}</CardDescription>
                  <CardDescription className="text-sm">{member.usn}</CardDescription>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">{member.phone}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="text-center animate-fade-in-up">
            <p className="text-muted-foreground mb-2">In collaboration with</p>
            <div className="flex flex-wrap justify-center gap-4 text-sm">
              <Badge variant="outline" className="border-secondary/30 text-secondary">
                IBM SkillsBuild
              </Badge>
              <Badge variant="outline" className="border-secondary/30 text-secondary">
                AWS India Tech Alliance
              </Badge>
              <Badge variant="outline" className="border-secondary/30 text-secondary">
                MITB ACM Student Chapter
              </Badge>
            </div>
          </div>
        </div>
      </section>

      <section id="overview" ref={setSectionRef("overview")} className="py-24 section-animate opacity-0 translate-y-5">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-20 animate-fade-in-up stagger-animate">
            <h2 className="text-5xl md:text-6xl font-bold mb-8 text-secondary">The Global Crisis</h2>
            <p className="text-2xl text-muted-foreground max-w-4xl mx-auto text-pretty leading-relaxed">
              Money laundering fuels terrorism, drug trade, corruption, and economic instability. Traditional AML
              systems are failing against sophisticated criminal networks.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8 mb-20">
            {[
              { icon: Target, title: "$2+ Trillion", desc: "Global illicit flows annually", color: "text-red-400" },
              { icon: Eye, title: "90%+", desc: "Of laundering goes undetected", color: "text-orange-400" },
              { icon: TrendingUp, title: "95%", desc: "False positives in current systems", color: "text-yellow-400" },
              { icon: Shield, title: "Billions", desc: "In fines due to compliance gaps", color: "text-secondary" },
            ].map((stat, index) => (
              <Card
                key={index}
                className="text-center interactive-hover transition-all duration-700 hover:border-secondary/50 animate-fade-in-up group bg-card/50 backdrop-blur-sm stagger-animate animate-glow-pulse"
                style={{ animationDelay: `${index * 0.1}s` }}
              >
                <CardContent className="pt-8 pb-6">
                  <div className="relative mb-6">
                    <stat.icon
                      className={`h-16 w-16 ${stat.color} mx-auto group-hover:scale-125 transition-transform duration-500`}
                    />
                    <div className="absolute inset-0 bg-secondary/10 rounded-full blur-xl group-hover:blur-2xl transition-all duration-500" />
                  </div>
                  <h3 className="text-3xl font-bold mb-3 text-secondary group-hover:text-primary transition-colors duration-500">
                    {stat.title}
                  </h3>
                  <p className="text-muted-foreground leading-relaxed">{stat.desc}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="text-center animate-fade-in-up stagger-animate">
            <h3 className="text-3xl font-bold mb-8 text-secondary">Why Traditional Systems Fail</h3>
            <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
              {[
                { title: "Rigid Rules", desc: "Static rule-based engines can't adapt to evolving criminal tactics" },
                { title: "Data Silos", desc: "Fragmented systems create blind spots across borders and institutions" },
                { title: "Slow Response", desc: "Criminals innovate faster than banks and regulators can adapt" },
              ].map((item, index) => (
                <div
                  key={index}
                  className="text-center animate-fade-in-up stagger-animate interactive-hover"
                  style={{ animationDelay: `${index * 0.2}s` }}
                >
                  <h4 className="text-xl font-semibold mb-3 text-secondary">{item.title}</h4>
                  <p className="text-muted-foreground">{item.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Problem Statement */}
      <section
        id="problem"
        ref={setSectionRef("problem")}
        className="py-20 bg-muted/30 section-animate opacity-0 translate-y-5"
      >
        <div className="max-w-6xl mx-auto px-6">
          <h2 className="text-4xl font-bold text-center mb-12 animate-fade-in-up">Problem Statement</h2>
          <div className="grid lg:grid-cols-2 gap-12 items-center">
            <div className="animate-slide-in-left">
              <h3 className="text-2xl font-bold mb-6 text-secondary">Traditional AML Fails</h3>
              <div className="space-y-4">
                <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                  <div className="w-2 h-2 bg-secondary rounded-full mt-2 flex-shrink-0 animate-pulse" />
                  <p>Rigid rule-based engines → up to 95% false positives</p>
                </div>
                <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                  <div className="w-2 h-2 bg-secondary rounded-full mt-2 flex-shrink-0 animate-pulse" />
                  <p>Fragmented data silos → blind spots across borders</p>
                </div>
                <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                  <div className="w-2 h-2 bg-secondary rounded-full mt-2 flex-shrink-0 animate-pulse" />
                  <p>Slow adaptability → criminals innovate faster than banks/regulators</p>
                </div>
              </div>
            </div>
            <Card className="p-8 animate-slide-in-right hover:shadow-xl transition-all duration-500 hover:scale-105 hover:border-secondary/50">
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <Network className="h-6 w-6 text-secondary animate-pulse" />
                  <span>Our Theme</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="hover:translate-x-2 transition-transform duration-300">
                  <h4 className="font-semibold mb-2 text-secondary">GAN Powered AML Intelligence</h4>
                  <p className="text-sm text-muted-foreground">
                    Graph neural networks + Generative AI: Uncover hidden mule networks
                  </p>
                </div>
                <div className="hover:translate-x-2 transition-transform duration-300">
                  <h4 className="font-semibold mb-2 text-secondary">Agentic AI & RAG</h4>
                  <p className="text-sm text-muted-foreground">
                    Deliver actionable risk metrics through SARs with autonomous capability
                  </p>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      <section
        id="solution"
        ref={setSectionRef("solution")}
        className="py-24 bg-card/30 border-y border-secondary/10 section-animate opacity-0 translate-y-5"
      >
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-20 animate-fade-in-up stagger-animate">
            <h2 className="text-5xl md:text-6xl font-bold mb-8 text-secondary">FinTrace Solution</h2>
            <p className="text-2xl text-muted-foreground max-w-5xl mx-auto text-pretty leading-relaxed">
              An end-to-end evolving Graph AML and Mule Radar platform that combines cutting-edge AI technologies to
              create an adaptive, intelligent detection ecosystem
            </p>
          </div>

          <div className="grid lg:grid-cols-3 gap-10 mb-20">
            {[
              {
                icon: Brain,
                title: "GAN-Based Red Team",
                desc: "Generates synthetic fraud scenarios to train detection systems on emerging patterns that don't yet exist in real data",
                features: ["Adversarial Training", "Pattern Simulation", "Future-Proof Detection"],
              },
              {
                icon: Network,
                title: "Graph Neural Networks",
                desc: "Models financial transactions as dynamic graphs, revealing hidden relationships and mule communities",
                features: ["Community Detection", "Relationship Mapping", "Network Analysis"],
              },
              {
                icon: Zap,
                title: "Agentic AI Orchestrator",
                desc: "Intelligent system that continuously analyzes alerts, refines thresholds, and generates actionable insights",
                features: ["Autonomous Investigation", "Alert Prioritization", "Continuous Learning"],
              },
            ].map((feature, index) => (
              <Card
                key={index}
                className="interactive-hover transition-all duration-700 hover:border-secondary/50 animate-fade-in-up group bg-card/50 backdrop-blur-sm stagger-animate animate-glow-pulse"
                style={{ animationDelay: `${index * 0.2}s` }}
              >
                <CardHeader className="pb-4">
                  <div className="relative mb-6">
                    <feature.icon className="h-16 w-16 text-secondary mb-4 group-hover:scale-125 group-hover:text-accent transition-all duration-500 mx-auto" />
                    <div className="absolute inset-0 bg-secondary/10 rounded-full blur-xl group-hover:blur-2xl transition-all duration-500" />
                  </div>
                  <CardTitle className="text-2xl group-hover:text-secondary transition-colors duration-500 text-center">
                    {feature.title}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-muted-foreground leading-relaxed">{feature.desc}</p>
                  <div className="space-y-2">
                    {feature.features.map((feat, idx) => (
                      <div
                        key={idx}
                        className="flex items-center space-x-2 hover:translate-x-2 transition-transform duration-300"
                      >
                        <div className="w-2 h-2 bg-secondary rounded-full animate-pulse" />
                        <span className="text-sm text-muted-foreground">{feat}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="mt-20">
            <h3 className="text-4xl font-bold text-center mb-12 text-secondary">Key Outcomes</h3>
            <div className="grid lg:grid-cols-2 gap-8">
              <Card className="p-8 bg-secondary/10 border-secondary/30 hover:bg-secondary/15 transition-all duration-500 animate-fade-in-up interactive-hover">
                <CardHeader>
                  <CardTitle className="text-2xl text-secondary flex items-center gap-3">
                    <TrendingUp className="h-8 w-8" />
                    Performance Improvements
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                    <div className="w-3 h-3 bg-secondary rounded-full mt-2 animate-pulse" />
                    <div>
                      <h4 className="font-semibold text-secondary">Reduced False Positives</h4>
                      <p className="text-muted-foreground">
                        Contextual understanding minimizes false alerts by up to 80%
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                    <div className="w-3 h-3 bg-secondary rounded-full mt-2 animate-pulse" />
                    <div>
                      <h4 className="font-semibold text-secondary">Enhanced Detection</h4>
                      <p className="text-muted-foreground">
                        Increases true positive detection of sophisticated mule networks
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="p-8 bg-secondary/10 border-secondary/30 hover:bg-secondary/15 transition-all duration-500 animate-fade-in-up interactive-hover">
                <CardHeader>
                  <CardTitle className="text-2xl text-secondary flex items-center gap-3">
                    <Zap className="h-8 w-8" />
                    Operational Benefits
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                    <div className="w-3 h-3 bg-secondary rounded-full mt-2 animate-pulse" />
                    <div>
                      <h4 className="font-semibold text-secondary">Accelerated Productivity</h4>
                      <p className="text-muted-foreground">
                        AI-generated summaries boost investigator efficiency by 60%
                      </p>
                    </div>
                  </div>
                  <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                    <div className="w-3 h-3 bg-secondary rounded-full mt-2 animate-pulse" />
                    <div>
                      <h4 className="font-semibold text-secondary">Enhanced Security</h4>
                      <p className="text-muted-foreground">
                        Strengthens trust in financial systems and reduces fraud losses
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </section>

      <section
        id="architecture"
        ref={setSectionRef("architecture")}
        className="py-24 bg-muted/30 section-animate opacity-0 translate-y-5"
      >
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-20">
            <h2 className="text-5xl md:text-6xl font-bold mb-8 text-secondary">System Architecture</h2>
            <p className="text-xl text-muted-foreground max-w-4xl mx-auto">
              A three-phase intelligent system that investigates, reports, and continuously learns from financial
              transaction patterns
            </p>
          </div>

          <div className="space-y-12">
            {/* Phase 1: Investigate */}
            <div className="relative">
              <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-secondary/30"></div>
              <Card className="ml-16 overflow-hidden hover:shadow-xl transition-all duration-500 hover:border-secondary/50 animate-fade-in-up bg-card/50 backdrop-blur-sm">
                <CardHeader className="bg-gradient-to-r from-secondary/20 to-secondary/10 border-b border-secondary/20 py-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-secondary/20 rounded-full flex items-center justify-center">
                      <span className="text-xl font-bold text-secondary">1</span>
                    </div>
                    <div>
                      <CardTitle className="text-2xl text-secondary">Phase 1: Investigate</CardTitle>
                      <CardDescription className="text-base text-muted-foreground">
                        GAN + Detector Engine
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-6 pb-6">
                  <p className="text-base mb-4 text-muted-foreground">
                    Generate Risk Scores and Ring Candidates from incoming transaction flows using advanced AI
                    simulation
                  </p>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="space-y-3">
                      <h4 className="text-lg font-semibold text-secondary">Input Processing</h4>
                      <div className="space-y-1.5">
                        <div className="flex items-center space-x-2 text-sm">
                          <Database className="h-4 w-4 text-secondary" />
                          <span>Incremental transaction flows</span>
                        </div>
                        <div className="flex items-center space-x-2 text-sm">
                          <Network className="h-4 w-4 text-secondary" />
                          <span>Identity links (Account ↔ Device/IP)</span>
                        </div>
                        <div className="flex items-center space-x-2 text-sm">
                          <TrendingUp className="h-4 w-4 text-secondary" />
                          <span>Rolling features (velocity, ratios)</span>
                        </div>
                      </div>
                    </div>
                    <div className="space-y-3">
                      <h4 className="text-lg font-semibold text-secondary">AI Processing</h4>
                      <div className="space-y-1.5">
                        <div className="flex items-center space-x-2 text-sm">
                          <Brain className="h-4 w-4 text-secondary" />
                          <span>Red Team (GAN) simulates mule tactics</span>
                        </div>
                        <div className="flex items-center space-x-2 text-sm">
                          <Shield className="h-4 w-4 text-secondary" />
                          <span>Blue Team (Detector) with GraphSAGE</span>
                        </div>
                        <div className="flex items-center space-x-2 text-sm">
                          <Users className="h-4 w-4 text-secondary" />
                          <span>Community detection for clusters</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 p-3 bg-secondary/10 rounded-lg">
                    <h5 className="font-semibold text-secondary mb-1 text-sm">Output:</h5>
                    <p className="text-xs text-muted-foreground">
                      Risk Score Array → Risk Label: Safe | Suspicious | Likely Mule | Confirmed Ring
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Phase 2: Report */}
            <div className="relative">
              <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-secondary/30"></div>
              <Card className="ml-16 overflow-hidden hover:shadow-xl transition-all duration-500 hover:border-secondary/50 animate-fade-in-up bg-card/50 backdrop-blur-sm">
                <CardHeader className="bg-gradient-to-r from-secondary/20 to-secondary/10 border-b border-secondary/20 py-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-secondary/20 rounded-full flex items-center justify-center">
                      <span className="text-xl font-bold text-secondary">2</span>
                    </div>
                    <div>
                      <CardTitle className="text-2xl text-secondary">Phase 2: Report</CardTitle>
                      <CardDescription className="text-base text-muted-foreground">RAG + SAR Generator</CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-6 pb-6">
                  <p className="text-base mb-4 text-muted-foreground">
                    Convert detections into evidence-backed compliance reports using intelligent retrieval and
                    generation
                  </p>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="space-y-3">
                      <h4 className="text-lg font-semibold text-secondary">RAG Processing</h4>
                      <div className="space-y-1.5">
                        <div className="flex items-center space-x-2 text-sm">
                          <Database className="h-4 w-4 text-secondary" />
                          <span>Case embedding in Vector DB</span>
                        </div>
                        <div className="flex items-center space-x-2 text-sm">
                          <Brain className="h-4 w-4 text-secondary" />
                          <span>RAG retrieval of similar cases</span>
                        </div>
                        <div className="flex items-center space-x-2 text-sm">
                          <FileText className="h-4 w-4 text-secondary" />
                          <span>Policy and typology matching</span>
                        </div>
                      </div>
                    </div>
                    <div className="space-y-3">
                      <h4 className="text-lg font-semibold text-secondary">SAR Generation</h4>
                      <div className="space-y-1.5">
                        <div className="flex items-center space-x-2 text-sm">
                          <FileText className="h-4 w-4 text-secondary" />
                          <span>Overview (who/what/when)</span>
                        </div>
                        <div className="flex items-center space-x-2 text-sm">
                          <TrendingUp className="h-4 w-4 text-secondary" />
                          <span>Evidence table with metrics</span>
                        </div>
                        <div className="flex items-center space-x-2 text-sm">
                          <Network className="h-4 w-4 text-secondary" />
                          <span>Graph snapshot with captions</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 p-3 bg-secondary/10 rounded-lg">
                    <h5 className="font-semibold text-secondary mb-1 text-sm">Output:</h5>
                    <p className="text-xs text-muted-foreground">
                      SAR (PDF/JSON) with confidence scores and full audit trail with citations
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Phase 3: Dig Deeper */}
            <div className="relative">
              <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-secondary/30"></div>
              <Card className="ml-16 overflow-hidden hover:shadow-xl transition-all duration-500 hover:border-secondary/50 animate-fade-in-up bg-card/50 backdrop-blur-sm">
                <CardHeader className="bg-gradient-to-r from-secondary/20 to-secondary/10 border-b border-secondary/20 py-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-secondary/20 rounded-full flex items-center justify-center">
                      <span className="text-xl font-bold text-secondary">3</span>
                    </div>
                    <div>
                      <CardTitle className="text-2xl text-secondary">Phase 3: Dig Deeper</CardTitle>
                      <CardDescription className="text-base text-muted-foreground">
                        Agentic Investigator
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="pt-6 pb-6">
                  <p className="text-base mb-4 text-muted-foreground">
                    Run autonomous follow-ups and what-if simulations with intelligent agent capabilities
                  </p>
                  <div className="grid md:grid-cols-2 gap-4">
                    <div className="space-y-3">
                      <h4 className="text-lg font-semibold text-secondary">Agent Skills</h4>
                      <div className="space-y-1.5">
                        <div className="flex items-center space-x-2 text-sm">
                          <Network className="h-4 w-4 text-secondary" />
                          <span>Expand graph hops & recompute</span>
                        </div>
                        <div className="flex items-center space-x-2 text-sm">
                          <Brain className="h-4 w-4 text-secondary" />
                          <span>Re-run GAN what-if scenarios</span>
                        </div>
                        <div className="flex items-center space-x-2 text-sm">
                          <Database className="h-4 w-4 text-secondary" />
                          <span>Retrieve prior rings with RAG</span>
                        </div>
                      </div>
                    </div>
                    <div className="space-y-3">
                      <h4 className="text-lg font-semibold text-secondary">Guardrails</h4>
                      <div className="space-y-1.5">
                        <div className="flex items-center space-x-2 text-sm">
                          <Shield className="h-4 w-4 text-secondary" />
                          <span>Max 3 autonomous steps per cycle</span>
                        </div>
                        <div className="flex items-center space-x-2 text-sm">
                          <Users className="h-4 w-4 text-secondary" />
                          <span>Human approval before alerts</span>
                        </div>
                        <div className="flex items-center space-x-2 text-sm">
                          <Zap className="h-4 w-4 text-secondary" />
                          <span>Rate limits on AI calls</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="mt-4 p-3 bg-secondary/10 rounded-lg">
                    <h5 className="font-semibold text-secondary mb-1 text-sm">Output:</h5>
                    <p className="text-xs text-muted-foreground">
                      Follow-up memo with delta updates, refreshed scores, and watchlist of linked accounts
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>
          </div>
        </div>
      </section>

      <section ref={setSectionRef("technology")} className="py-24 section-animate opacity-0 translate-y-5">
        <div className="max-w-7xl mx-auto px-6">
          <div className="text-center mb-20">
            <h2 className="text-5xl md:text-6xl font-bold mb-8 text-secondary">Technology Stack</h2>
            <p className="text-xl text-muted-foreground max-w-4xl mx-auto">
              Cutting-edge AI and machine learning technologies powering the next generation of AML detection
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
            {[
              {
                name: "GAN Technology",
                desc: "Generative Adversarial Networks for synthetic fraud pattern simulation",
                icon: Brain,
                features: ["Red Team Simulation", "Adversarial Training", "Pattern Generation"],
              },
              {
                name: "Data Prep Kit",
                desc: "Synthetic mule data generation and balanced dataset creation",
                icon: Database,
                features: ["Synthetic Data", "Scenario Coverage", "Benchmarking"],
              },
              {
                name: "IBM Granite",
                desc: "LLM-powered compliance assistant for SAR generation",
                icon: Cpu,
                features: ["Auto-SAR Drafting", "Pattern Summarization", "Explainable AI"],
              },
              {
                name: "RAG Pipeline",
                desc: "Retrieval-Augmented Generation for fraud case analysis",
                icon: Network,
                features: ["Case Retrieval", "Enhanced Explainability", "SAR Enrichment"],
              },
              {
                name: "Agentic AI",
                desc: "Always-on compliance analyst with autonomous capabilities",
                icon: Bot,
                features: ["24/7 Monitoring", "Dig Deeper Mode", "Continuous Learning"],
              },
              {
                name: "Graph Neural Networks",
                desc: "Advanced network analysis for mule ring detection",
                icon: Network,
                features: ["GraphSAGE/GAT", "Community Detection", "Relationship Mapping"],
              },
            ].map((tech, index) => (
              <Card
                key={index}
                className="interactive-hover transition-all duration-700 hover:border-secondary/50 animate-fade-in-up group bg-card/50 backdrop-blur-sm"
                style={{ animationDelay: `${index * 0.1}s` }}
              >
                <CardHeader className="text-center">
                  <div className="relative mb-4">
                    <tech.icon className="h-16 w-16 text-secondary mx-auto group-hover:scale-125 transition-transform duration-500" />
                    <div className="absolute inset-0 bg-secondary/10 rounded-full blur-xl group-hover:blur-2xl transition-all duration-500" />
                  </div>
                  <CardTitle className="text-xl group-hover:text-secondary transition-colors duration-500">
                    {tech.name}
                  </CardTitle>
                  <CardDescription className="text-muted-foreground">{tech.desc}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {tech.features.map((feature, idx) => (
                      <div
                        key={idx}
                        className="flex items-center space-x-2 hover:translate-x-2 transition-transform duration-300"
                      >
                        <div className="w-2 h-2 bg-secondary rounded-full animate-pulse" />
                        <span className="text-sm text-muted-foreground">{feature}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* Impact Section */}
      <section
        id="impact"
        ref={setSectionRef("impact")}
        className="py-20 bg-muted/30 section-animate opacity-0 translate-y-5"
      >
        <div className="max-w-6xl mx-auto px-6">
          <h2 className="text-4xl font-bold text-center mb-12 animate-fade-in-up">Impact</h2>
          <div className="grid lg:grid-cols-2 gap-12">
            <Card className="p-8 hover:shadow-xl transition-all duration-500 hover:scale-105 hover:border-secondary/50 animate-slide-in-left">
              <CardHeader>
                <CardTitle className="text-2xl text-secondary">Business Impact</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                  <TrendingUp className="h-5 w-5 text-secondary mt-1 flex-shrink-0 animate-pulse" />
                  <p>Lesser false positives → lower compliance costs</p>
                </div>
                <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                  <Shield className="h-5 w-5 text-secondary mt-1 flex-shrink-0 animate-pulse" />
                  <p>Faster mule ring detection → reduced risk exposure</p>
                </div>
                <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                  <Network className="h-5 w-5 text-secondary mt-1 flex-shrink-0 animate-pulse" />
                  <p>Scalable across banks, fintechs, wallets</p>
                </div>
                <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                  <FileText className="h-5 w-5 text-secondary mt-1 flex-shrink-0 animate-pulse" />
                  <p>Auto-SAR reports → regulatory safety + fewer fines</p>
                </div>
              </CardContent>
            </Card>

            <Card className="p-8 hover:shadow-xl transition-all duration-500 hover:scale-105 hover:border-secondary/50 animate-slide-in-right">
              <CardHeader>
                <CardTitle className="text-2xl text-secondary">Social Impact</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                  <Shield className="h-5 w-5 text-secondary mt-1 flex-shrink-0 animate-pulse" />
                  <p>Blocks laundering → cuts crime & terror funding</p>
                </div>
                <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                  <Users className="h-5 w-5 text-secondary mt-1 flex-shrink-0 animate-pulse" />
                  <p>Protects citizens from mule exploitation</p>
                </div>
                <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                  <TrendingUp className="h-5 w-5 text-secondary mt-1 flex-shrink-0 animate-pulse" />
                  <p>Builds trust in digital finance systems</p>
                </div>
                <div className="flex items-start space-x-3 hover:translate-x-2 transition-transform duration-300">
                  <Target className="h-5 w-5 text-secondary mt-1 flex-shrink-0 animate-pulse" />
                  <p>Strengthens national security against cross-border fraud</p>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer
        ref={setSectionRef("footer")}
        className="py-12 border-t border-border bg-primary/5 section-animate opacity-0 translate-y-5"
      >
        <div className="max-w-6xl mx-auto px-6 text-center animate-fade-in-up">
          <div className="flex items-center justify-center space-x-2 mb-6">
            <Shield className="h-8 w-8 text-secondary animate-pulse-glow" />
            <span className="text-2xl font-bold">FinTrace</span>
          </div>
          <p className="text-muted-foreground mb-6">
            In collaboration with IBM SkillsBuild and AWS India Tech Alliance
          </p>
          <p className="text-sm text-muted-foreground">
            Manipal Academy of Higher Education, Bengaluru • Manipal Institute of Technology, Bengaluru
          </p>
          <p className="text-sm text-muted-foreground mt-2">
            School of Computer Engineering & MITB ACM Student Chapter
          </p>
        </div>
      </footer>
    </div>
  )
}
