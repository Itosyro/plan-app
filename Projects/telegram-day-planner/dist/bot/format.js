export function formatSummary(result) {
    const parts = [];
    const taskCount = result.extractedTasks?.length || 0;
    const noteCount = result.extractedNotes?.length || 0;
    const projectCount = result.extractedProjects?.length || 0;
    if (taskCount === 0 && noteCount === 0) {
        return '🤔 Не удалось выделить задачи. Попробуйте переформулировать.';
    }
    // Counts
    const counts = [];
    if (taskCount > 0)
        counts.push(`${taskCount} ${pluralize(taskCount, 'задача', 'задачи', 'задач')}`);
    if (noteCount > 0)
        counts.push(`${noteCount} ${pluralize(noteCount, 'заметка', 'заметки', 'заметок')}`);
    parts.push(`✅ Разобрал: ${counts.join(', ')}`);
    // Summary
    if (result.summary) {
        parts.push(`\n💡 ${result.summary}`);
    }
    // Top tasks
    const todayTasks = (result.extractedTasks || [])
        .filter((t) => t.statusSuggestion === 'today')
        .slice(0, 3);
    const highPriority = (result.extractedTasks || [])
        .filter((t) => t.priority === 'high' && t.statusSuggestion !== 'today')
        .slice(0, 3);
    if (todayTasks.length > 0) {
        parts.push('\n🔥 *На сегодня:*');
        todayTasks.forEach((t, i) => {
            parts.push(`${i + 1}. ${t.title}`);
        });
    }
    if (highPriority.length > 0 && todayTasks.length < 3) {
        const remaining = 3 - todayTasks.length;
        parts.push('\n⭐ *Важное:*');
        highPriority.slice(0, remaining).forEach((t, i) => {
            parts.push(`${i + 1}. ${t.title}`);
        });
    }
    // Clarifying questions
    if (result.clarifyingQuestions?.length > 0) {
        parts.push('\n❓ Уточнения:');
        result.clarifyingQuestions.slice(0, 2).forEach((q) => {
            parts.push(`• ${q.question}`);
        });
    }
    return parts.join('\n');
}
function pluralize(n, one, few, many) {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod100 >= 11 && mod100 <= 19)
        return many;
    if (mod10 === 1)
        return one;
    if (mod10 >= 2 && mod10 <= 4)
        return few;
    return many;
}
