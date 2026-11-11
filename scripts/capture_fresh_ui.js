// Paste into the local application's browser console once. Submit Q1-Q3 through
// the visible UI, then call captureFootballQuestion('Q1'), etc. Full text stays
// local; saveFootballCapture downloads it for the ignored .runtime/ directory.
window.footballUiCapture = [];
window.captureFootballQuestion = (questionId) => {
  const value = {
    question_id: questionId,
    captured_at: new Date().toISOString(),
    url: location.href,
    bot: [...document.querySelectorAll('[data-testid="bot"]')].map(x => ({tag: x.tagName, text: x.innerText})),
    panels: [...document.querySelectorAll('details')]
      .filter(x => /^L\d/.test(x.querySelector('summary')?.innerText || ''))
      .map(x => ({summary: x.querySelector('summary').innerText, text: x.innerText})),
    links: [...document.querySelectorAll('a[href*="wikipedia.org"]')].map(x => ({text: x.innerText, href: x.href})),
    resources_tab: [...document.querySelectorAll('[role="tab"]')].some(x => x.innerText === 'Resources'),
  };
  window.footballUiCapture.push(value);
  return {question_id: questionId, answers: value.bot.length, panels: value.panels.length};
};
window.saveFootballCapture = () => {
  const url = URL.createObjectURL(new Blob([JSON.stringify(window.footballUiCapture, null, 2)], {type: 'application/json'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'ui-three-dom.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
