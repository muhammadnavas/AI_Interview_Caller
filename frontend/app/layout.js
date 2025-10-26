import './globals.css'

export const metadata = {
	title: 'AI Interview Scheduler',
	description: 'Automated interview scheduling',
}

export default function RootLayout({ children }) {
	return (
		<html lang="en">
			<body>
				{children}
			</body>
		</html>
	)
}
