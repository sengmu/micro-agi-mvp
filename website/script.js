// Micro-AGI Landing Page Interactive Scripts

document.addEventListener('DOMContentLoaded', () => {
    // Smooth scrolling for navigation links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth'
                });
            }
        });
    });

    // Subtly animate diagram nodes on hover
    const diagNodes = document.querySelectorAll('.diag-node');
    diagNodes.forEach(node => {
        node.addEventListener('mouseenter', () => {
            node.style.transform = 'scale(1.03) translateY(-2px)';
        });
        node.style.transition = 'all 0.3s ease';
        node.addEventListener('mouseleave', () => {
            node.style.transform = 'scale(1) translateY(0)';
        });
    });

    console.log("Micro-AGI marketing landing loaded successfully.");
});
