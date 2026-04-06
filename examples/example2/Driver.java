public class Driver {

    public static void main(String[] args) {
        Person cotterell = new Person("Michael", "Cotterell", "Dr.");
        CourseOffering offering0 = new CourseOffering("CSCI 1302", cotterell, Semester.SPRING, 2026);
        System.out.println(offering0);
    } // main

} // Driver

class Person {

    private String firstName;
    private String lastName;
    private String honorific;

    public Person(String firstName, String lastName, String honorific) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.honorific = honorific;
    } // Person

    public Person(String firstName, String lastName) {
        this(firstName, lastName, null);
    } // Person

    public Person(Person otherPerson) {
        this.firstName = otherPerson.firstName;
        this.lastName = otherPerson.lastName;
        this.honorific = otherPerson.honorific;
    } // Person
    
    public String getFirstName() {
        return this.firstName;
    } // getFirstName

    public String getLastName() {
        return this.lastName;
    } // getLastName    

    public String getHonorific() {
        return this.honorific;
    } // getHonorific

    public void setFirstName(String firstName) {
        this.firstName = firstName;
    } // setFirstName

    public void setLastName(String lastName) {
        this.lastName = lastName;
    } // setLastName    

    public void setHonorific(String honorific) {
        this.honorific = honorific;
    } // setHonorific

    public String getFullName() {
        String fullName = this.firstName + " " + this.lastName;
        if (this.honorific != null) {
            fullName = this.honorific + " " + fullName;
        } // if
        return fullName;
    } // getFullName

    public String toString() {
	return this.getFullName();
    } // toString
    
} // Person

enum Semester {
    SPRING, SUMMER, FALL;
} // Semester

class CourseOffering {
    
    private String courseName;
    private Person instructor;
    private Semester semester;
    private int year;    

    public CourseOffering(String courseName, Person instructor, Semester semester, int year) {
        this.courseName = courseName;
        this.instructor = new Person(instructor);
        this.semester = semester;
        this.year = year;
    } // CourseOffering

    public String getCourseName() {
        return this.courseName;
    } // getCourseName

    public Person getInstructor() {
        return this.instructor;
    } // getPerson
    
    public Semester getSemester() {
        return this.semester;
    } // getSemester

    public int getYear() {
        return this.year;
    } // getYear

    public String toString() {
        return String.format("%s (%s %s) with %s", this.courseName, this.semester, this.year, this.instructor);
    } // toString
    
} // CourseOffering

