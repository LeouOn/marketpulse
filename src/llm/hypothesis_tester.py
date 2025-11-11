"""Hypothesis Testing Framework for Trading Strategies
Structured approach to testing trading hypotheses with LLM assistance
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from loguru import logger

from .trading_knowledge_rag import TradingKnowledgeRAG, get_trading_rag
from .system_prompts import HYPOTHESIS_TESTING_PROMPT, build_enhanced_prompt


@dataclass
class HypothesisTestResult:
    """Structured result from hypothesis testing"""
    hypothesis_name: str
    timestamp: str
    status: str  # 'confirmed', 'refuted', 'inconclusive', 'needs_more_data'
    confidence: float  # 0-100
    summary: str
    key_findings: List[str]
    statistical_evidence: Dict[str, Any]
    trading_implications: str
    further_testing_needed: List[str]
    raw_analysis: str
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2)


class HypothesisTester:
    """Test trading hypotheses with LLM assistance"""
    
    def __init__(self, llm_client, knowledge_rag: Optional[TradingKnowledgeRAG] = None):
        self.llm_client = llm_client
        self.knowledge_rag = knowledge_rag or get_trading_rag()
        self.hypotheses_dir = Path("trading_knowledge/hypotheses")
        
        logger.info("HypothesisTester initialized")
    
    def load_hypothesis(self, hypothesis_name: str) -> Optional[Dict[str, Any]]:
        """
        Load hypothesis from markdown file
        
        Args:
            hypothesis_name: Name of hypothesis file (without .md)
            
        Returns:
            Dictionary with hypothesis details or None
        """
        # Try active hypotheses first
        active_path = self.hypotheses_dir / "active" / f"{hypothesis_name}.md"
        if active_path.exists():
            try:
                content = active_path.read_text(encoding='utf-8')
                return self._parse_hypothesis_md(content, hypothesis_name, 'active')
            except Exception as e:
                logger.error(f"Error loading active hypothesis {hypothesis_name}: {e}")
        
        # Try tested hypotheses
        tested_path = self.hypotheses_dir / "tested" / f"{hypothesis_name}.md"
        if tested_path.exists():
            try:
                content = tested_path.read_text(encoding='utf-8')
                return self._parse_hypothesis_md(content, hypothesis_name, 'tested')
            except Exception as e:
                logger.error(f"Error loading tested hypothesis {hypothesis_name}: {e}")
        
        logger.warning(f"Hypothesis {hypothesis_name} not found")
        return None
    
    def _parse_hypothesis_md(self, content: str, name: str, status: str) -> Dict[str, Any]:
        """Parse hypothesis markdown into structured format"""
        hypothesis = {
            'name': name,
            'status': status,
            'description': '',
            'background': '',
            'mechanism': '',
            'what_to_look_for': [],
            'testing_criteria': {},
            'related_concepts': [],
            'confounding_factors': [],
            'trading_implications': '',
            'data_requirements': {},
            'success_metrics': [],
            'raw_content': content
        }
        
        # Extract sections using markdown headers
        sections = re.split(r'^##\s+', content, flags=re.MULTILINE)
        
        for section in sections:
            if not section.strip():
                continue
            
            # Get section title (first line)
            lines = section.strip().split('\n')
            title = lines[0].strip()
            content = '\n'.join(lines[1:]).strip()
            
            if 'Hypothesis Statement' in title or 'Hypothesis' in title:
                hypothesis['description'] = content
            elif 'Background' in title:
                hypothesis['background'] = content
            elif 'Mechanism' in title:
                hypothesis['mechanism'] = content
            elif 'What to Look For' in title:
                hypothesis['what_to_look_for'] = self._parse_bullet_points(content)
            elif 'Testing Criteria' in title:
                hypothesis['testing_criteria'] = self._parse_criteria(content)
            elif 'Related Concepts' in title:
                hypothesis['related_concepts'] = self._parse_bullet_points(content)
            elif 'Confounding Factors' in title:
                hypothesis['confounding_factors'] = self._parse_bullet_points(content)
            elif 'Trading Implications' in title:
                hypothesis['trading_implications'] = content
            elif 'Data Requirements' in title:
                hypothesis['data_requirements'] = self._parse_data_requirements(content)
            elif 'Success Metrics' in title:
                hypothesis['success_metrics'] = self._parse_bullet_points(content)
        
        return hypothesis
    
    def _parse_bullet_points(self, content: str) -> List[str]:
        """Parse bullet points from markdown content"""
        bullets = []
        for line in content.split('\n'):
            line = line.strip()
            if line.startswith('-') or line.startswith('*'):
                bullets.append(line[1:].strip())
            elif re.match(r'^\d+\.', line):
                bullets.append(re.sub(r'^\d+\.\s*', '', line))
        return bullets
    
    def _parse_criteria(self, content: str) -> Dict[str, Any]:
        """Parse testing criteria section"""
        criteria = {}
        current_key = None
        
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            if line.startswith('**') and ':' in line:
                # Key-value pair
                key_val = line.replace('**', '').split(':', 1)
                if len(key_val) == 2:
                    key = key_val[0].strip().lower().replace(' ', '_')
                    val = key_val[1].strip()
                    
                    # Try to convert to number
                    try:
                        if '.' in val:
                            val = float(val)
                        else:
                            val = int(val)
                    except:
                        pass
                    
                    criteria[key] = val
                    current_key = key
            elif line.startswith('-') and current_key:
                # Additional bullet under current key
                if current_key not in criteria:
                    criteria[current_key] = []
                if not isinstance(criteria[current_key], list):
                    criteria[current_key] = [criteria[current_key]]
                criteria[current_key].append(line[1:].strip())
        
        return criteria
    
    def _parse_data_requirements(self, content: str) -> Dict[str, Any]:
        """Parse data requirements section"""
        requirements = {
            'instruments': [],
            'timeframe': '',
            'features': [],
            'control': ''
        }
        
        for line in content.split('\n'):
            line = line.strip()
            if not line or not line.startswith('-'):
                continue
            
            line = line[1:].strip()
            if ':' in line:
                key, val = line.split(':', 1)
                key = key.strip().lower()
                val = val.strip()
                
                if 'instrument' in key:
                    requirements['instruments'].extend([v.strip() for v in val.split(',')])
                elif 'timeframe' in key:
                    requirements['timeframe'] = val
                elif 'feature' in key:
                    requirements['features'].extend([v.strip() for v in val.split(',')])
                elif 'control' in key:
                    requirements['control'] = val
        
        return requirements
    
    async def clarify_hypothesis(self, hypothesis: Dict[str, Any]) -> str:
        """
        Ask LLM to clarify and structure the hypothesis
        
        Args:
            hypothesis: Hypothesis dictionary
            
        Returns:
            LLM clarification and structuring
        """
        # Get relevant knowledge context
        context_chunks = self.knowledge_rag.retrieve_context(hypothesis['description'])
        
        # Build prompt
        prompt = build_enhanced_prompt(
            HYPOTHESIS_TESTING_PROMPT,
            context_chunks,
            hypothesis['description']
        )
        
        # Query LLM
        messages = [{'role': 'user', 'content': prompt}]
        
        response = await self.llm_client.generate_completion(
            model='deep_analysis',
            messages=messages,
            max_tokens=500,
            temperature=0.3
        )
        
        if response and 'choices' in response:
            return response['choices'][0]['message']['content']
        
        return "Failed to get clarification from LLM"
    
    async def analyze_hypothesis_with_data(self, hypothesis: Dict[str, Any], market_data: Dict[str, Any]) -> str:
        """
        Analyze hypothesis with actual market data
        
        Args:
            hypothesis: Hypothesis dictionary
            market_data: Market data for analysis
            
        Returns:
            LLM analysis of hypothesis vs data
        """
        # Get relevant context
        context_chunks = self.knowledge_rag.retrieve_context(hypothesis['description'])
        
        # Build data summary
        data_summary = f"""
        HYPOTHESIS: {hypothesis['description']}
        
        TESTING CRITERIA: {json.dumps(hypothesis['testing_criteria'], indent=2)}
        
        MARKET DATA:
        {json.dumps(market_data, indent=2)}
        
        SUCCESS METRICS: {', '.join(hypothesis['success_metrics'])}
        """
        
        # Build prompt
        prompt = build_enhanced_prompt(
            HYPOTHESIS_TESTING_PROMPT,
            context_chunks,
            hypothesis['description'],
            market_data
        )
        
        # Query LLM
        messages = [{'role': 'user', 'content': prompt}]
        
        response = await self.llm_client.generate_completion(
            model='deep_analysis',
            messages=messages,
            max_tokens=600,
            temperature=0.3
        )
        
        if response and 'choices' in response:
            return response['choices'][0]['message']['content']
        
        return "Failed to get analysis from LLM"
    
    async def test_hypothesis(self, hypothesis_name: str, market_data: Optional[Dict[str, Any]] = None) -> HypothesisTestResult:
        """
        Full hypothesis testing workflow
        
        Args:
            hypothesis_name: Name of hypothesis to test
            market_data: Optional market data for analysis
            
        Returns:
            Structured test results
        """
        logger.info(f"Testing hypothesis: {hypothesis_name}")
        
        # Load hypothesis
        hypothesis = self.load_hypothesis(hypothesis_name)
        if not hypothesis:
            return HypothesisTestResult(
                hypothesis_name=hypothesis_name,
                timestamp=datetime.now().isoformat(),
                status="error",
                confidence=0,
                summary=f"Hypothesis {hypothesis_name} not found",
                key_findings=[],
                statistical_evidence={},
                trading_implications="",
                further_testing_needed=[],
                raw_analysis=""
            )
        
        # Phase 1: Clarify hypothesis (if no data provided)
        if market_data is None:
            clarification = await self.clarify_hypothesis(hypothesis)
            return HypothesisTestResult(
                hypothesis_name=hypothesis_name,
                timestamp=datetime.now().isoformat(),
                status="clarified",
                confidence=50,
                summary="Hypothesis clarified, awaiting data for full analysis",
                key_findings=["Hypothesis structure analyzed"],
                statistical_evidence={},
                trading_implications="",
                further_testing_needed=["Collect market data as per requirements"],
                raw_analysis=clarification
            )
        
        # Phase 2: Analyze with data
        analysis = await self.analyze_hypothesis_with_data(hypothesis, market_data)
        
        # Phase 3: Parse results into structured format
        result = self._parse_analysis_results(hypothesis_name, analysis, market_data)
        
        logger.info(f"Hypothesis test completed: {result.status} ({result.confidence}% confidence)")
        return result
    
    def _parse_analysis_results(self, hypothesis_name: str, analysis: str, market_data: Dict[str, Any]) -> HypothesisTestResult:
        """Parse LLM analysis into structured results"""
        # Default values
        status = "inconclusive"
        confidence = 50
        summary = "Analysis completed"
        key_findings = []
        statistical_evidence = {}
        trading_implications = ""
        further_testing_needed = []
        
        # Try to extract structured information from analysis
        lines = analysis.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Look for confidence statements
            if 'confidence' in line.lower() or 'confident' in line.lower():
                # Extract numeric confidence
                numbers = re.findall(r'\d+', line)
                if numbers:
                    confidence = int(numbers[0])
            
            # Look for conclusion statements
            if any(word in line.lower() for word in ['confirm', 'support', 'validate']):
                status = "confirmed"
                summary = line
            elif any(word in line.lower() for word in ['refute', 'reject', 'disprove']):
                status = "refuted"
                summary = line
            
            # Look for key findings (bullet points)
            if line.startswith('-') or line.startswith('*'):
                key_findings.append(line[1:].strip())
            
            # Look for statistical evidence
            if any(stat in line.lower() for stat in ['p-value', 'correlation', 'significance', 'probability']):
                statistical_evidence['statistical_note'] = line
        
        # If no clear status determined, analyze confidence
        if status == "inconclusive" and confidence > 70:
            status = "likely_confirmed"
        elif status == "inconclusive" and confidence < 30:
            status = "likely_refuted"
        
        return HypothesisTestResult(
            hypothesis_name=hypothesis_name,
            timestamp=datetime.now().isoformat(),
            status=status,
            confidence=confidence,
            summary=summary,
            key_findings=key_findings,
            statistical_evidence=statistical_evidence,
            trading_implications=trading_implications,
            further_testing_needed=further_testing_needed,
            raw_analysis=analysis
        )
    
    def list_hypotheses(self) -> List[Dict[str, str]]:
        """List all available hypotheses"""
        hypotheses = []
        
        # Check active hypotheses
        active_dir = self.hypotheses_dir / "active"
        if active_dir.exists():
            for md_file in active_dir.glob("*.md"):
                hypotheses.append({
                    'name': md_file.stem,
                    'status': 'active',
                    'file': str(md_file)
                })
        
        # Check tested hypotheses
        tested_dir = self.hypotheses_dir / "tested"
        if tested_dir.exists():
            for md_file in tested_dir.glob("*.md"):
                hypotheses.append({
                    'name': md_file.stem,
                    'status': 'tested',
                    'file': str(md_file)
                })
        
        return hypotheses
    
    def archive_hypothesis(self, hypothesis_name: str) -> bool:
        """Move hypothesis from active to tested"""
        active_path = self.hypotheses_dir / "active" / f"{hypothesis_name}.md"
        tested_path = self.hypotheses_dir / "tested" / f"{hypothesis_name}.md"
        
        if active_path.exists():
            try:
                # Ensure tested directory exists
                tested_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Move file
                active_path.rename(tested_path)
                logger.info(f"Archived hypothesis: {hypothesis_name}")
                return True
            except Exception as e:
                logger.error(f"Error archiving hypothesis {hypothesis_name}: {e}")
        
        return False


# Example usage and testing
async def test_hypothesis_framework():
    """Test the hypothesis framework"""
    from .llm_client import LMStudioClient
    
    async with LMStudioClient() as client:
        tester = HypothesisTester(client)
        
        # List available hypotheses
        hypotheses = tester.list_hypotheses()
        print(f"Available hypotheses: {[h['name'] for h in hypotheses]}")
        
        # Test overnight margin cascade hypothesis
        if any(h['name'] == 'overnight_margin_cascade' for h in hypotheses):
            print("\nTesting overnight margin cascade hypothesis...")
            
            # Sample market data (would be real data in production)
            sample_data = {
                'btc_perp': {
                    'price': 45000,
                    'change_24h': 2.5,
                    'volume_24h': 1200000000,
                    'funding_rate': 0.01,
                    'open_interest': 850000000
                },
                'time_window': {
                    'start': '23:45:00',
                    'end': '00:15:00',
                    'price_change': -0.8,
                    'volume_spike': 2.3
                }
            }
            
            result = await tester.test_hypothesis('overnight_margin_cascade', sample_data)
            print(f"\nTest Result: {result.status} ({result.confidence}% confidence)")
            print(f"Summary: {result.summary}")
            print(f"Key Findings: {result.key_findings}")
            
            # Save results
            results_file = Path(f"hypothesis_results_{result.hypothesis_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
            results_file.write_text(result.to_json())
            print(f"\nResults saved to: {results_file}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_hypothesis_framework())