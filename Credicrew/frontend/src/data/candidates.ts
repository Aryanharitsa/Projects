export type Candidate = {
  id: number; name: string; score: number;
  role: string; location: string;
  tags: string[]; keywords: string[];
  headline: string; cv: string;
};
export const candidates: Candidate[] = [
  {
    "id": 1,
    "name": "Ananya Rao",
    "score": 75,
    "role": "Frontend Engineer",
    "location": "Bengaluru",
    "tags": [
      "React",
      "Next.js",
      "Tailwind"
    ],
    "keywords": [
      "React",
      "Next.js",
      "Tailwind"
    ],
    "headline": "Frontend Engineer • Bengaluru",
    "cv": "# Ananya Rao\n\n**Role**: Frontend Engineer\n**Location**: Bengaluru\n**Skills**: React, Next.js, Tailwind\n\n## Summary\nEngineer with 2+ years building frontend engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 1: Used React, Next.js, Tailwind."
  },
  {
    "id": 2,
    "name": "Aarav Jain",
    "score": 82,
    "role": "Full-stack Engineer",
    "location": "Remote (IN)",
    "tags": [
      "Next.js",
      "Node.js",
      "Prisma"
    ],
    "keywords": [
      "Next.js",
      "Node.js",
      "Prisma"
    ],
    "headline": "Full-stack Engineer • Remote (IN)",
    "cv": "# Aarav Jain\n\n**Role**: Full-stack Engineer\n**Location**: Remote (IN)\n**Skills**: Next.js, Node.js, Prisma\n\n## Summary\nEngineer with 3+ years building full-stack engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 2: Used Next.js, Node.js, Prisma."
  },
  {
    "id": 3,
    "name": "Kavya Rao",
    "score": 89,
    "role": "Data Engineer",
    "location": "Mumbai",
    "tags": [
      "Python",
      "Airflow",
      "SQL"
    ],
    "keywords": [
      "Python",
      "Airflow",
      "SQL"
    ],
    "headline": "Data Engineer • Mumbai",
    "cv": "# Kavya Rao\n\n**Role**: Data Engineer\n**Location**: Mumbai\n**Skills**: Python, Airflow, SQL\n\n## Summary\nEngineer with 4+ years building data engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 3: Used Python, Airflow, SQL."
  },
  {
    "id": 4,
    "name": "Rohan Bhatt",
    "score": 96,
    "role": "DevOps Engineer",
    "location": "Pune",
    "tags": [
      "AWS",
      "Terraform",
      "CI/CD"
    ],
    "keywords": [
      "AWS",
      "Terraform",
      "CI/CD"
    ],
    "headline": "DevOps Engineer • Pune",
    "cv": "# Rohan Bhatt\n\n**Role**: DevOps Engineer\n**Location**: Pune\n**Skills**: AWS, Terraform, CI/CD\n\n## Summary\nEngineer with 5+ years building devops engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 4: Used AWS, Terraform, CI/CD."
  },
  {
    "id": 5,
    "name": "Vedant K",
    "score": 78,
    "role": "GenAI Engineer",
    "location": "Delhi NCR",
    "tags": [
      "LangChain",
      "OpenAI",
      "Vector DBs"
    ],
    "keywords": [
      "LangChain",
      "OpenAI",
      "Vector DBs"
    ],
    "headline": "GenAI Engineer • Delhi NCR",
    "cv": "# Vedant K\n\n**Role**: GenAI Engineer\n**Location**: Delhi NCR\n**Skills**: LangChain, OpenAI, Vector DBs\n\n## Summary\nEngineer with 6+ years building genai engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 5: Used LangChain, OpenAI, Vector DBs."
  },
  {
    "id": 6,
    "name": "Neha Kulkarni",
    "score": 85,
    "role": "ML Engineer",
    "location": "Kolkata",
    "tags": [
      "PyTorch",
      "Transformers",
      "LLMs"
    ],
    "keywords": [
      "PyTorch",
      "Transformers",
      "LLMs"
    ],
    "headline": "ML Engineer • Kolkata",
    "cv": "# Neha Kulkarni\n\n**Role**: ML Engineer\n**Location**: Kolkata\n**Skills**: PyTorch, Transformers, LLMs\n\n## Summary\nEngineer with 7+ years building ml engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 1: Used PyTorch, Transformers, LLMs."
  },
  {
    "id": 7,
    "name": "Mahima Gupta",
    "score": 92,
    "role": "Platform Engineer",
    "location": "Hyderabad",
    "tags": [
      "Kubernetes",
      "Kafka",
      "Observability"
    ],
    "keywords": [
      "Kubernetes",
      "Kafka",
      "Observability"
    ],
    "headline": "Platform Engineer • Hyderabad",
    "cv": "# Mahima Gupta\n\n**Role**: Platform Engineer\n**Location**: Hyderabad\n**Skills**: Kubernetes, Kafka, Observability\n\n## Summary\nEngineer with 8+ years building platform engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 2: Used Kubernetes, Kafka, Observability."
  },
  {
    "id": 8,
    "name": "Omkar R",
    "score": 99,
    "role": "NLP Engineer",
    "location": "Chennai",
    "tags": [
      "spaCy",
      "HF Transformers",
      "T5"
    ],
    "keywords": [
      "spaCy",
      "HF Transformers",
      "T5"
    ],
    "headline": "NLP Engineer • Chennai",
    "cv": "# Omkar R\n\n**Role**: NLP Engineer\n**Location**: Chennai\n**Skills**: spaCy, HF Transformers, T5\n\n## Summary\nEngineer with 9+ years building nlp engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 3: Used spaCy, HF Transformers, T5."
  },
  {
    "id": 9,
    "name": "Karthik Menon",
    "score": 81,
    "role": "GenAI Engineer",
    "location": "Bengaluru",
    "tags": [
      "Function Calling",
      "Agents",
      "Eval"
    ],
    "keywords": [
      "Function Calling",
      "Agents",
      "Eval"
    ],
    "headline": "GenAI Engineer • Bengaluru",
    "cv": "# Karthik Menon\n\n**Role**: GenAI Engineer\n**Location**: Bengaluru\n**Skills**: Function Calling, Agents, Eval\n\n## Summary\nEngineer with 2+ years building genai engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 4: Used Function Calling, Agents, Eval."
  },
  {
    "id": 10,
    "name": "Priya Sethi",
    "score": 88,
    "role": "Product Designer",
    "location": "Remote (IN)",
    "tags": [
      "Figma",
      "Design Systems",
      "Prototyping"
    ],
    "keywords": [
      "Figma",
      "Design Systems",
      "Prototyping"
    ],
    "headline": "Product Designer • Remote (IN)",
    "cv": "# Priya Sethi\n\n**Role**: Product Designer\n**Location**: Remote (IN)\n**Skills**: Figma, Design Systems, Prototyping\n\n## Summary\nEngineer with 3+ years building product designer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 5: Used Figma, Design Systems, Prototyping."
  },
  {
    "id": 11,
    "name": "Soham Deshpande",
    "score": 95,
    "role": "Frontend Engineer",
    "location": "Mumbai",
    "tags": [
      "React",
      "Next.js",
      "Tailwind"
    ],
    "keywords": [
      "React",
      "Next.js",
      "Tailwind"
    ],
    "headline": "Frontend Engineer • Mumbai",
    "cv": "# Soham Deshpande\n\n**Role**: Frontend Engineer\n**Location**: Mumbai\n**Skills**: React, Next.js, Tailwind\n\n## Summary\nEngineer with 4+ years building frontend engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 1: Used React, Next.js, Tailwind."
  },
  {
    "id": 12,
    "name": "Krupa J",
    "score": 77,
    "role": "Full-stack Engineer",
    "location": "Pune",
    "tags": [
      "Next.js",
      "Node.js",
      "Prisma"
    ],
    "keywords": [
      "Next.js",
      "Node.js",
      "Prisma"
    ],
    "headline": "Full-stack Engineer • Pune",
    "cv": "# Krupa J\n\n**Role**: Full-stack Engineer\n**Location**: Pune\n**Skills**: Next.js, Node.js, Prisma\n\n## Summary\nEngineer with 5+ years building full-stack engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 2: Used Next.js, Node.js, Prisma."
  },
  {
    "id": 13,
    "name": "Dev Patel",
    "score": 84,
    "role": "Data Engineer",
    "location": "Delhi NCR",
    "tags": [
      "Python",
      "Airflow",
      "SQL"
    ],
    "keywords": [
      "Python",
      "Airflow",
      "SQL"
    ],
    "headline": "Data Engineer • Delhi NCR",
    "cv": "# Dev Patel\n\n**Role**: Data Engineer\n**Location**: Delhi NCR\n**Skills**: Python, Airflow, SQL\n\n## Summary\nEngineer with 6+ years building data engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 3: Used Python, Airflow, SQL."
  },
  {
    "id": 14,
    "name": "Parth Rawat",
    "score": 91,
    "role": "DevOps Engineer",
    "location": "Kolkata",
    "tags": [
      "AWS",
      "Terraform",
      "CI/CD"
    ],
    "keywords": [
      "AWS",
      "Terraform",
      "CI/CD"
    ],
    "headline": "DevOps Engineer • Kolkata",
    "cv": "# Parth Rawat\n\n**Role**: DevOps Engineer\n**Location**: Kolkata\n**Skills**: AWS, Terraform, CI/CD\n\n## Summary\nEngineer with 7+ years building devops engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 4: Used AWS, Terraform, CI/CD."
  },
  {
    "id": 15,
    "name": "Jahnavi D",
    "score": 98,
    "role": "GenAI Engineer",
    "location": "Hyderabad",
    "tags": [
      "LangChain",
      "OpenAI",
      "Vector DBs"
    ],
    "keywords": [
      "LangChain",
      "OpenAI",
      "Vector DBs"
    ],
    "headline": "GenAI Engineer • Hyderabad",
    "cv": "# Jahnavi D\n\n**Role**: GenAI Engineer\n**Location**: Hyderabad\n**Skills**: LangChain, OpenAI, Vector DBs\n\n## Summary\nEngineer with 8+ years building genai engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 5: Used LangChain, OpenAI, Vector DBs."
  },
  {
    "id": 16,
    "name": "Vikram Iyer",
    "score": 80,
    "role": "ML Engineer",
    "location": "Chennai",
    "tags": [
      "PyTorch",
      "Transformers",
      "LLMs"
    ],
    "keywords": [
      "PyTorch",
      "Transformers",
      "LLMs"
    ],
    "headline": "ML Engineer • Chennai",
    "cv": "# Vikram Iyer\n\n**Role**: ML Engineer\n**Location**: Chennai\n**Skills**: PyTorch, Transformers, LLMs\n\n## Summary\nEngineer with 9+ years building ml engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 1: Used PyTorch, Transformers, LLMs."
  },
  {
    "id": 17,
    "name": "Aditya Bansal",
    "score": 87,
    "role": "Platform Engineer",
    "location": "Bengaluru",
    "tags": [
      "Kubernetes",
      "Kafka",
      "Observability"
    ],
    "keywords": [
      "Kubernetes",
      "Kafka",
      "Observability"
    ],
    "headline": "Platform Engineer • Bengaluru",
    "cv": "# Aditya Bansal\n\n**Role**: Platform Engineer\n**Location**: Bengaluru\n**Skills**: Kubernetes, Kafka, Observability\n\n## Summary\nEngineer with 2+ years building platform engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 2: Used Kubernetes, Kafka, Observability."
  },
  {
    "id": 18,
    "name": "Armaan K",
    "score": 94,
    "role": "NLP Engineer",
    "location": "Remote (IN)",
    "tags": [
      "spaCy",
      "HF Transformers",
      "T5"
    ],
    "keywords": [
      "spaCy",
      "HF Transformers",
      "T5"
    ],
    "headline": "NLP Engineer • Remote (IN)",
    "cv": "# Armaan K\n\n**Role**: NLP Engineer\n**Location**: Remote (IN)\n**Skills**: spaCy, HF Transformers, T5\n\n## Summary\nEngineer with 3+ years building nlp engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 3: Used spaCy, HF Transformers, T5."
  },
  {
    "id": 19,
    "name": "Ishita Verma",
    "score": 76,
    "role": "GenAI Engineer",
    "location": "Mumbai",
    "tags": [
      "Function Calling",
      "Agents",
      "Eval"
    ],
    "keywords": [
      "Function Calling",
      "Agents",
      "Eval"
    ],
    "headline": "GenAI Engineer • Mumbai",
    "cv": "# Ishita Verma\n\n**Role**: GenAI Engineer\n**Location**: Mumbai\n**Skills**: Function Calling, Agents, Eval\n\n## Summary\nEngineer with 4+ years building genai engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 4: Used Function Calling, Agents, Eval."
  },
  {
    "id": 20,
    "name": "Tejas Shah",
    "score": 83,
    "role": "Product Designer",
    "location": "Pune",
    "tags": [
      "Figma",
      "Design Systems",
      "Prototyping"
    ],
    "keywords": [
      "Figma",
      "Design Systems",
      "Prototyping"
    ],
    "headline": "Product Designer • Pune",
    "cv": "# Tejas Shah\n\n**Role**: Product Designer\n**Location**: Pune\n**Skills**: Figma, Design Systems, Prototyping\n\n## Summary\nEngineer with 5+ years building product designer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 5: Used Figma, Design Systems, Prototyping."
  },
  {
    "id": 21,
    "name": "Riya Shah",
    "score": 90,
    "role": "Frontend Engineer",
    "location": "Delhi NCR",
    "tags": [
      "React",
      "Next.js",
      "Tailwind"
    ],
    "keywords": [
      "React",
      "Next.js",
      "Tailwind"
    ],
    "headline": "Frontend Engineer • Delhi NCR",
    "cv": "# Riya Shah\n\n**Role**: Frontend Engineer\n**Location**: Delhi NCR\n**Skills**: React, Next.js, Tailwind\n\n## Summary\nEngineer with 6+ years building frontend engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 1: Used React, Next.js, Tailwind."
  },
  {
    "id": 22,
    "name": "Aditi Nair",
    "score": 97,
    "role": "Full-stack Engineer",
    "location": "Kolkata",
    "tags": [
      "Next.js",
      "Node.js",
      "Prisma"
    ],
    "keywords": [
      "Next.js",
      "Node.js",
      "Prisma"
    ],
    "headline": "Full-stack Engineer • Kolkata",
    "cv": "# Aditi Nair\n\n**Role**: Full-stack Engineer\n**Location**: Kolkata\n**Skills**: Next.js, Node.js, Prisma\n\n## Summary\nEngineer with 7+ years building full-stack engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 2: Used Next.js, Node.js, Prisma."
  },
  {
    "id": 23,
    "name": "Sanjana N",
    "score": 79,
    "role": "Data Engineer",
    "location": "Hyderabad",
    "tags": [
      "Python",
      "Airflow",
      "SQL"
    ],
    "keywords": [
      "Python",
      "Airflow",
      "SQL"
    ],
    "headline": "Data Engineer • Hyderabad",
    "cv": "# Sanjana N\n\n**Role**: Data Engineer\n**Location**: Hyderabad\n**Skills**: Python, Airflow, SQL\n\n## Summary\nEngineer with 8+ years building data engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 3: Used Python, Airflow, SQL."
  },
  {
    "id": 24,
    "name": "Harsh Agrawal",
    "score": 86,
    "role": "DevOps Engineer",
    "location": "Chennai",
    "tags": [
      "AWS",
      "Terraform",
      "CI/CD"
    ],
    "keywords": [
      "AWS",
      "Terraform",
      "CI/CD"
    ],
    "headline": "DevOps Engineer • Chennai",
    "cv": "# Harsh Agrawal\n\n**Role**: DevOps Engineer\n**Location**: Chennai\n**Skills**: AWS, Terraform, CI/CD\n\n## Summary\nEngineer with 9+ years building devops engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 4: Used AWS, Terraform, CI/CD."
  },
  {
    "id": 25,
    "name": "Sneha Patil",
    "score": 93,
    "role": "GenAI Engineer",
    "location": "Bengaluru",
    "tags": [
      "LangChain",
      "OpenAI",
      "Vector DBs"
    ],
    "keywords": [
      "LangChain",
      "OpenAI",
      "Vector DBs"
    ],
    "headline": "GenAI Engineer • Bengaluru",
    "cv": "# Sneha Patil\n\n**Role**: GenAI Engineer\n**Location**: Bengaluru\n**Skills**: LangChain, OpenAI, Vector DBs\n\n## Summary\nEngineer with 2+ years building genai engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 5: Used LangChain, OpenAI, Vector DBs."
  },
  {
    "id": 26,
    "name": "Tanvi P",
    "score": 75,
    "role": "ML Engineer",
    "location": "Remote (IN)",
    "tags": [
      "PyTorch",
      "Transformers",
      "LLMs"
    ],
    "keywords": [
      "PyTorch",
      "Transformers",
      "LLMs"
    ],
    "headline": "ML Engineer • Remote (IN)",
    "cv": "# Tanvi P\n\n**Role**: ML Engineer\n**Location**: Remote (IN)\n**Skills**: PyTorch, Transformers, LLMs\n\n## Summary\nEngineer with 3+ years building ml engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 1: Used PyTorch, Transformers, LLMs."
  },
  {
    "id": 27,
    "name": "Meera Kapoor",
    "score": 82,
    "role": "Platform Engineer",
    "location": "Mumbai",
    "tags": [
      "Kubernetes",
      "Kafka",
      "Observability"
    ],
    "keywords": [
      "Kubernetes",
      "Kafka",
      "Observability"
    ],
    "headline": "Platform Engineer • Mumbai",
    "cv": "# Meera Kapoor\n\n**Role**: Platform Engineer\n**Location**: Mumbai\n**Skills**: Kubernetes, Kafka, Observability\n\n## Summary\nEngineer with 4+ years building platform engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 2: Used Kubernetes, Kafka, Observability."
  },
  {
    "id": 28,
    "name": "Aakash M",
    "score": 89,
    "role": "NLP Engineer",
    "location": "Pune",
    "tags": [
      "spaCy",
      "HF Transformers",
      "T5"
    ],
    "keywords": [
      "spaCy",
      "HF Transformers",
      "T5"
    ],
    "headline": "NLP Engineer • Pune",
    "cv": "# Aakash M\n\n**Role**: NLP Engineer\n**Location**: Pune\n**Skills**: spaCy, HF Transformers, T5\n\n## Summary\nEngineer with 5+ years building nlp engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 3: Used spaCy, HF Transformers, T5."
  },
  {
    "id": 29,
    "name": "Nikhil Singh",
    "score": 96,
    "role": "GenAI Engineer",
    "location": "Delhi NCR",
    "tags": [
      "Function Calling",
      "Agents",
      "Eval"
    ],
    "keywords": [
      "Function Calling",
      "Agents",
      "Eval"
    ],
    "headline": "GenAI Engineer • Delhi NCR",
    "cv": "# Nikhil Singh\n\n**Role**: GenAI Engineer\n**Location**: Delhi NCR\n**Skills**: Function Calling, Agents, Eval\n\n## Summary\nEngineer with 6+ years building genai engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 4: Used Function Calling, Agents, Eval."
  },
  {
    "id": 30,
    "name": "Pranav S",
    "score": 78,
    "role": "Product Designer",
    "location": "Kolkata",
    "tags": [
      "Figma",
      "Design Systems",
      "Prototyping"
    ],
    "keywords": [
      "Figma",
      "Design Systems",
      "Prototyping"
    ],
    "headline": "Product Designer • Kolkata",
    "cv": "# Pranav S\n\n**Role**: Product Designer\n**Location**: Kolkata\n**Skills**: Figma, Design Systems, Prototyping\n\n## Summary\nEngineer with 7+ years building product designer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 5: Used Figma, Design Systems, Prototyping."
  },
  {
    "id": 31,
    "name": "Shruti Gandhi",
    "score": 85,
    "role": "Frontend Engineer",
    "location": "Hyderabad",
    "tags": [
      "React",
      "Next.js",
      "Tailwind"
    ],
    "keywords": [
      "React",
      "Next.js",
      "Tailwind"
    ],
    "headline": "Frontend Engineer • Hyderabad",
    "cv": "# Shruti Gandhi\n\n**Role**: Frontend Engineer\n**Location**: Hyderabad\n**Skills**: React, Next.js, Tailwind\n\n## Summary\nEngineer with 8+ years building frontend engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 1: Used React, Next.js, Tailwind."
  },
  {
    "id": 32,
    "name": "Aparna S",
    "score": 92,
    "role": "Full-stack Engineer",
    "location": "Chennai",
    "tags": [
      "Next.js",
      "Node.js",
      "Prisma"
    ],
    "keywords": [
      "Next.js",
      "Node.js",
      "Prisma"
    ],
    "headline": "Full-stack Engineer • Chennai",
    "cv": "# Aparna S\n\n**Role**: Full-stack Engineer\n**Location**: Chennai\n**Skills**: Next.js, Node.js, Prisma\n\n## Summary\nEngineer with 9+ years building full-stack engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 2: Used Next.js, Node.js, Prisma."
  },
  {
    "id": 33,
    "name": "Yash U",
    "score": 99,
    "role": "Data Engineer",
    "location": "Bengaluru",
    "tags": [
      "Python",
      "Airflow",
      "SQL"
    ],
    "keywords": [
      "Python",
      "Airflow",
      "SQL"
    ],
    "headline": "Data Engineer • Bengaluru",
    "cv": "# Yash U\n\n**Role**: Data Engineer\n**Location**: Bengaluru\n**Skills**: Python, Airflow, SQL\n\n## Summary\nEngineer with 2+ years building data engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 3: Used Python, Airflow, SQL."
  },
  {
    "id": 34,
    "name": "Rohit Agarwal",
    "score": 81,
    "role": "DevOps Engineer",
    "location": "Remote (IN)",
    "tags": [
      "AWS",
      "Terraform",
      "CI/CD"
    ],
    "keywords": [
      "AWS",
      "Terraform",
      "CI/CD"
    ],
    "headline": "DevOps Engineer • Remote (IN)",
    "cv": "# Rohit Agarwal\n\n**Role**: DevOps Engineer\n**Location**: Remote (IN)\n**Skills**: AWS, Terraform, CI/CD\n\n## Summary\nEngineer with 3+ years building devops engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 4: Used AWS, Terraform, CI/CD."
  },
  {
    "id": 35,
    "name": "Pooja N",
    "score": 88,
    "role": "GenAI Engineer",
    "location": "Mumbai",
    "tags": [
      "LangChain",
      "OpenAI",
      "Vector DBs"
    ],
    "keywords": [
      "LangChain",
      "OpenAI",
      "Vector DBs"
    ],
    "headline": "GenAI Engineer • Mumbai",
    "cv": "# Pooja N\n\n**Role**: GenAI Engineer\n**Location**: Mumbai\n**Skills**: LangChain, OpenAI, Vector DBs\n\n## Summary\nEngineer with 4+ years building genai engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 5: Used LangChain, OpenAI, Vector DBs."
  },
  {
    "id": 36,
    "name": "Kabir Khan",
    "score": 95,
    "role": "ML Engineer",
    "location": "Pune",
    "tags": [
      "PyTorch",
      "Transformers",
      "LLMs"
    ],
    "keywords": [
      "PyTorch",
      "Transformers",
      "LLMs"
    ],
    "headline": "ML Engineer • Pune",
    "cv": "# Kabir Khan\n\n**Role**: ML Engineer\n**Location**: Pune\n**Skills**: PyTorch, Transformers, LLMs\n\n## Summary\nEngineer with 5+ years building ml engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 1: Used PyTorch, Transformers, LLMs."
  },
  {
    "id": 37,
    "name": "Ibrahim S",
    "score": 77,
    "role": "Platform Engineer",
    "location": "Delhi NCR",
    "tags": [
      "Kubernetes",
      "Kafka",
      "Observability"
    ],
    "keywords": [
      "Kubernetes",
      "Kafka",
      "Observability"
    ],
    "headline": "Platform Engineer • Delhi NCR",
    "cv": "# Ibrahim S\n\n**Role**: Platform Engineer\n**Location**: Delhi NCR\n**Skills**: Kubernetes, Kafka, Observability\n\n## Summary\nEngineer with 6+ years building platform engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 2: Used Kubernetes, Kafka, Observability."
  },
  {
    "id": 38,
    "name": "Mansi T",
    "score": 84,
    "role": "NLP Engineer",
    "location": "Kolkata",
    "tags": [
      "spaCy",
      "HF Transformers",
      "T5"
    ],
    "keywords": [
      "spaCy",
      "HF Transformers",
      "T5"
    ],
    "headline": "NLP Engineer • Kolkata",
    "cv": "# Mansi T\n\n**Role**: NLP Engineer\n**Location**: Kolkata\n**Skills**: spaCy, HF Transformers, T5\n\n## Summary\nEngineer with 7+ years building nlp engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 3: Used spaCy, HF Transformers, T5."
  },
  {
    "id": 39,
    "name": "Ira Sharma",
    "score": 91,
    "role": "GenAI Engineer",
    "location": "Hyderabad",
    "tags": [
      "Function Calling",
      "Agents",
      "Eval"
    ],
    "keywords": [
      "Function Calling",
      "Agents",
      "Eval"
    ],
    "headline": "GenAI Engineer • Hyderabad",
    "cv": "# Ira Sharma\n\n**Role**: GenAI Engineer\n**Location**: Hyderabad\n**Skills**: Function Calling, Agents, Eval\n\n## Summary\nEngineer with 8+ years building genai engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 4: Used Function Calling, Agents, Eval."
  },
  {
    "id": 40,
    "name": "Dhruv Chawla",
    "score": 98,
    "role": "Product Designer",
    "location": "Chennai",
    "tags": [
      "Figma",
      "Design Systems",
      "Prototyping"
    ],
    "keywords": [
      "Figma",
      "Design Systems",
      "Prototyping"
    ],
    "headline": "Product Designer • Chennai",
    "cv": "# Dhruv Chawla\n\n**Role**: Product Designer\n**Location**: Chennai\n**Skills**: Figma, Design Systems, Prototyping\n\n## Summary\nEngineer with 9+ years building product designer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 5: Used Figma, Design Systems, Prototyping."
  },
  {
    "id": 41,
    "name": "Samar Khatri",
    "score": 80,
    "role": "Frontend Engineer",
    "location": "Bengaluru",
    "tags": [
      "React",
      "Next.js",
      "Tailwind"
    ],
    "keywords": [
      "React",
      "Next.js",
      "Tailwind"
    ],
    "headline": "Frontend Engineer • Bengaluru",
    "cv": "# Samar Khatri\n\n**Role**: Frontend Engineer\n**Location**: Bengaluru\n**Skills**: React, Next.js, Tailwind\n\n## Summary\nEngineer with 2+ years building frontend engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 1: Used React, Next.js, Tailwind."
  },
  {
    "id": 42,
    "name": "Rehan Ali",
    "score": 87,
    "role": "Full-stack Engineer",
    "location": "Remote (IN)",
    "tags": [
      "Next.js",
      "Node.js",
      "Prisma"
    ],
    "keywords": [
      "Next.js",
      "Node.js",
      "Prisma"
    ],
    "headline": "Full-stack Engineer • Remote (IN)",
    "cv": "# Rehan Ali\n\n**Role**: Full-stack Engineer\n**Location**: Remote (IN)\n**Skills**: Next.js, Node.js, Prisma\n\n## Summary\nEngineer with 3+ years building full-stack engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 2: Used Next.js, Node.js, Prisma."
  },
  {
    "id": 43,
    "name": "Zara Qureshi",
    "score": 94,
    "role": "Data Engineer",
    "location": "Mumbai",
    "tags": [
      "Python",
      "Airflow",
      "SQL"
    ],
    "keywords": [
      "Python",
      "Airflow",
      "SQL"
    ],
    "headline": "Data Engineer • Mumbai",
    "cv": "# Zara Qureshi\n\n**Role**: Data Engineer\n**Location**: Mumbai\n**Skills**: Python, Airflow, SQL\n\n## Summary\nEngineer with 4+ years building data engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 3: Used Python, Airflow, SQL."
  },
  {
    "id": 44,
    "name": "Ankit Sheikh",
    "score": 76,
    "role": "DevOps Engineer",
    "location": "Pune",
    "tags": [
      "AWS",
      "Terraform",
      "CI/CD"
    ],
    "keywords": [
      "AWS",
      "Terraform",
      "CI/CD"
    ],
    "headline": "DevOps Engineer • Pune",
    "cv": "# Ankit Sheikh\n\n**Role**: DevOps Engineer\n**Location**: Pune\n**Skills**: AWS, Terraform, CI/CD\n\n## Summary\nEngineer with 5+ years building devops engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 4: Used AWS, Terraform, CI/CD."
  },
  {
    "id": 45,
    "name": "Divya Reddy",
    "score": 83,
    "role": "GenAI Engineer",
    "location": "Delhi NCR",
    "tags": [
      "LangChain",
      "OpenAI",
      "Vector DBs"
    ],
    "keywords": [
      "LangChain",
      "OpenAI",
      "Vector DBs"
    ],
    "headline": "GenAI Engineer • Delhi NCR",
    "cv": "# Divya Reddy\n\n**Role**: GenAI Engineer\n**Location**: Delhi NCR\n**Skills**: LangChain, OpenAI, Vector DBs\n\n## Summary\nEngineer with 6+ years building genai engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 5: Used LangChain, OpenAI, Vector DBs."
  },
  {
    "id": 46,
    "name": "Varun Chandra",
    "score": 90,
    "role": "ML Engineer",
    "location": "Kolkata",
    "tags": [
      "PyTorch",
      "Transformers",
      "LLMs"
    ],
    "keywords": [
      "PyTorch",
      "Transformers",
      "LLMs"
    ],
    "headline": "ML Engineer • Kolkata",
    "cv": "# Varun Chandra\n\n**Role**: ML Engineer\n**Location**: Kolkata\n**Skills**: PyTorch, Transformers, LLMs\n\n## Summary\nEngineer with 7+ years building ml engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 1: Used PyTorch, Transformers, LLMs."
  },
  {
    "id": 47,
    "name": "Sanya Das",
    "score": 97,
    "role": "Platform Engineer",
    "location": "Hyderabad",
    "tags": [
      "Kubernetes",
      "Kafka",
      "Observability"
    ],
    "keywords": [
      "Kubernetes",
      "Kafka",
      "Observability"
    ],
    "headline": "Platform Engineer • Hyderabad",
    "cv": "# Sanya Das\n\n**Role**: Platform Engineer\n**Location**: Hyderabad\n**Skills**: Kubernetes, Kafka, Observability\n\n## Summary\nEngineer with 8+ years building platform engineer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 2: Used Kubernetes, Kafka, Observability."
  },
  {
    "id": 48,
    "name": "Kiran Roy",
    "score": 79,
    "role": "NLP Engineer",
    "location": "Chennai",
    "tags": [
      "spaCy",
      "HF Transformers",
      "T5"
    ],
    "keywords": [
      "spaCy",
      "HF Transformers",
      "T5"
    ],
    "headline": "NLP Engineer • Chennai",
    "cv": "# Kiran Roy\n\n**Role**: NLP Engineer\n**Location**: Chennai\n**Skills**: spaCy, HF Transformers, T5\n\n## Summary\nEngineer with 9+ years building nlp engineer solutions.\n\n## Experience\n- Company 3: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 3: Used spaCy, HF Transformers, T5."
  },
  {
    "id": 49,
    "name": "Mohan Mukherjee",
    "score": 86,
    "role": "GenAI Engineer",
    "location": "Bengaluru",
    "tags": [
      "Function Calling",
      "Agents",
      "Eval"
    ],
    "keywords": [
      "Function Calling",
      "Agents",
      "Eval"
    ],
    "headline": "GenAI Engineer • Bengaluru",
    "cv": "# Mohan Mukherjee\n\n**Role**: GenAI Engineer\n**Location**: Bengaluru\n**Skills**: Function Calling, Agents, Eval\n\n## Summary\nEngineer with 2+ years building genai engineer solutions.\n\n## Experience\n- Company 1: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 4: Used Function Calling, Agents, Eval."
  },
  {
    "id": 50,
    "name": "Ananya Rao",
    "score": 93,
    "role": "Product Designer",
    "location": "Remote (IN)",
    "tags": [
      "Figma",
      "Design Systems",
      "Prototyping"
    ],
    "keywords": [
      "Figma",
      "Design Systems",
      "Prototyping"
    ],
    "headline": "Product Designer • Remote (IN)",
    "cv": "# Ananya Rao\n\n**Role**: Product Designer\n**Location**: Remote (IN)\n**Skills**: Figma, Design Systems, Prototyping\n\n## Summary\nEngineer with 3+ years building product designer solutions.\n\n## Experience\n- Company 2: Built features and improved performance.\n- Led small pods; collaborated with PM/Design.\n\n## Projects\n- Project 5: Used Figma, Design Systems, Prototyping."
  }
];