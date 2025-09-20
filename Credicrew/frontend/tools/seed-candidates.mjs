import { writeFileSync } from 'fs';
const first = ["Ananya","Aarav","Kavya","Rohan","Vedant","Neha","Mahima","Omkar","Karthik","Priya","Soham","Krupa","Dev","Parth","Jahnavi","Vikram","Aditya","Armaan","Ishita","Tejas","Riya","Aditi","Sanjana","Harsh","Sneha","Tanvi","Meera","Aakash","Nikhil","Pranav","Shruti","Aparna","Yash","Rohit","Pooja","Kabir","Ibrahim","Mansi","Ira","Dhruv","Samar","Rehan","Zara","Ankit","Divya","Varun","Sanya","Kiran","Mohan"];
const last  = ["Rao","Jain","Rao","Bhatt","K","Kulkarni","Gupta","R","Menon","Sethi","Deshpande","J","Patel","Rawat","D","Iyer","Bansal","K","Verma","Shah","Shah","Nair","N","Agrawal","Patil","P","Kapoor","M","Singh","S","Gandhi","S","U","Agarwal","N","Khan","S","T","Sharma","Chawla","Khatri","Ali","Qureshi","Sheikh","Reddy","Chandra","Das","Roy","Mukherjee"];
const roles = [
  { title:"Frontend Engineer", tags:["React","Next.js","Tailwind"] },
  { title:"Full-stack Engineer", tags:["Next.js","Node.js","Prisma"] },
  { title:"Data Engineer", tags:["Python","Airflow","SQL"] },
  { title:"DevOps Engineer", tags:["AWS","Terraform","CI/CD"] },
  { title:"GenAI Engineer", tags:["LangChain","OpenAI","Vector DBs"] },
  { title:"ML Engineer", tags:["PyTorch","Transformers","LLMs"] },
  { title:"Platform Engineer", tags:["Kubernetes","Kafka","Observability"] },
  { title:"NLP Engineer", tags:["spaCy","HF Transformers","T5"] },
  { title:"GenAI Engineer", tags:["Function Calling","Agents","Eval"] },
  { title:"Product Designer", tags:["Figma","Design Systems","Prototyping"] },
];
const cities = ["Bengaluru","Pune","Hyderabad","Remote (IN)","Delhi NCR","Chennai","Mumbai","Kolkata"];
const rnd = (n)=>Math.floor(Math.random()*n);
const people = Array.from({length:50},(_,i)=>{
  const f = first[i%first.length], l = last[i%last.length];
  const r = roles[i%roles.length];
  const city = cities[(i*3)%cities.length];
  const score = 75 + (i*7)%25; // 75..99
  const id = i+1;
  const keywords = [...r.tags];
  const headline = `${r.title} • ${city}`;
  const cv = [
    `# ${f} ${l}`,
    ``,
    `**Role**: ${r.title}`,
    `**Location**: ${city}`,
    `**Skills**: ${r.tags.join(', ')}`,
    ``,
    `## Summary`,
    `Engineer with ${2 + (i%8)}+ years building ${r.title.toLowerCase()} solutions.`,
    ``,
    `## Experience`,
    `- Company ${(i%3)+1}: Built features and improved performance.`,
    `- Led small pods; collaborated with PM/Design.`,
    ``,
    `## Projects`,
    `- Project ${(i%5)+1}: Used ${r.tags.join(', ')}.`,
  ].join('\n');
  return { id, name:`${f} ${l}`, score, role:r.title, location:city, tags:r.tags, keywords, headline, cv };
});
const ts = `export type Candidate = {
  id: number; name: string; score: number;
  role: string; location: string;
  tags: string[]; keywords: string[];
  headline: string; cv: string;
};
export const candidates: Candidate[] = ${JSON.stringify(people, null, 2)};`;
writeFileSync('src/data/candidates.ts', ts);
console.log('Wrote src/data/candidates.ts with', people.length, 'candidates');
